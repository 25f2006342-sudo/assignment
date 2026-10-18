import os, re, json, calendar
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from flask import Flask, request, jsonify

app = Flask(__name__)
DATA_FILE = os.path.join(os.path.dirname(__file__), 'orders.jsonl')
RATES = {'USD': 1.0, 'EUR': 1.05, 'INR': 0.01107}
IST = ZoneInfo('Asia/Kolkata')
MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}
MONTHS.update({m.lower(): i for i, m in enumerate(calendar.month_abbr) if m})


def parse_dt(s):
    if not s: return None
    return datetime.fromisoformat(s.replace('Z', '+00:00')).astimezone(IST)

with open(DATA_FILE, encoding='utf-8') as f:
    raw_orders = [json.loads(line) for line in f if line.strip()]

# Current version of each order = row with latest updated_at.
current = {}
for row in raw_orders:
    oid = str(row.get('id', row.get('order_id', '')))
    stamp = parse_dt(row.get('updated_at')) or datetime.min.replace(tzinfo=IST)
    if oid not in current or stamp > (parse_dt(current[oid].get('updated_at')) or datetime.min.replace(tzinfo=IST)):
        current[oid] = row
orders = list(current.values())


def question_month_year(q):
    month = year = None
    for name, n in MONTHS.items():
        if re.search(r'\b' + re.escape(name) + r'\b', q, re.I):
            month = n; break
    m = re.search(r'\b(20\d{2})\b', q)
    if m: year = int(m.group(1))
    return month, year


def in_period(row, month, year):
    # Ledger reporting uses business date in Asia/Kolkata; created_at is the order business date.
    dt = parse_dt(row.get('created_at'))
    if dt is None: return False
    if year is not None and dt.year != year: return False
    if month is not None and dt.month != month: return False
    return True


def filter_orders(q):
    month, year = question_month_year(q)
    out = [r for r in orders if in_period(r, month, year)]
    regions = ['North', 'South', 'East', 'West', 'Central']
    for region in regions:
        if re.search(r'\b' + region + r'\b', q, re.I):
            out = [r for r in out if str(r.get('region','')).lower() == region.lower()]
            break
    products = sorted({str(r.get('product','')) for r in orders}, key=len, reverse=True)
    for product in products:
        if re.search(r'(?<!\w)' + re.escape(product) + r'(?!\w)', q, re.I):
            out = [r for r in out if str(r.get('product','')).lower() == product.lower()]
            break
    cust = re.search(r'\bC\d{3,5}\b', q, re.I)
    if cust:
        out = [r for r in out if str(r.get('customer','')).upper() == cust.group(0).upper()]
    oid = re.search(r'\bORD-\d+\b', q, re.I)
    if oid:
        out = [r for r in out if str(r.get('id','')).upper() == oid.group(0).upper()]
    return out


def usd_amount(r):
    return float(r.get('amount', 0) or 0) * RATES.get(str(r.get('currency','USD')).upper(), 1.0)


def answer(q):
    q0 = q.strip()
    low = q0.lower()
    rows = filter_orders(q0)
    # Explicit refund/refunded questions count only current refunded orders.
    if re.search(r'\b(refund|refunded|refunds)\b', low):
        rs = [r for r in rows if str(r.get('status','')).lower() == 'refunded']
        total = round(sum(usd_amount(r) for r in rs), 2)
        if re.search(r'\b(how many|number of|count|count of)\b', low):
            return len(rs)
        return total
    # Product with the highest revenue: aggregate paid USD-equivalent revenue per product.
    if (re.search(r'\b(product|products)\b', low)
            and re.search(r'\b(most|highest|top|maximum|max)\b', low)
            and re.search(r'\b(revenue|sales|turnover|earned|earnings)\b', low)):
        paid = [r for r in rows if str(r.get('status','')).lower() == 'paid']
        totals = {}
        for r in paid:
            name = str(r.get('product', ''))
            totals[name] = totals.get(name, 0.0) + usd_amount(r)
        if not totals:
            return ''
        return sorted(totals.items(), key=lambda x: (-x[1], x[0]))[0][0]

    # Revenue/sales means only paid current orders.
    if re.search(r'\b(revenue|sales|turnover|generated|generate|earned|earnings)\b', low):
        paid = [r for r in rows if str(r.get('status','')).lower() == 'paid']
        if re.search(r'\b(how many|number of|count|count of)\b', low):
            return len(paid)
        total = round(sum(usd_amount(r) for r in paid), 2)
        # If they ask for a product/customer breakdown, still return the aggregate for the matched subset.
        return total
    # Customer counts must be handled before generic order counts: questions such as
    # "How many customers placed at least one paid order?" ask for distinct people,
    # not the number of paid order rows.
    if re.search(r'\b(how many|number of|count|count of|unique|different)\b', low) and re.search(r'\bcustomer', low):
        if re.search(r'\bpaid\b', low): rows = [r for r in rows if str(r.get('status','')).lower() == 'paid']
        elif re.search(r'\brefunded\b|\brefund\b', low): rows = [r for r in rows if str(r.get('status','')).lower() == 'refunded']
        elif re.search(r'\bvoid\b', low): rows = [r for r in rows if str(r.get('status','')).lower() == 'void']
        return len({r.get('customer') for r in rows if r.get('customer')})
    # Counts of orders.
    if re.search(r'\b(how many|number of|count|count of)\b', low) and re.search(r'\b(order|orders|transaction|transactions)\b', low):
        if re.search(r'\bpaid\b', low): rows = [r for r in rows if str(r.get('status','')).lower() == 'paid']
        elif re.search(r'\bvoid\b', low): rows = [r for r in rows if str(r.get('status','')).lower() == 'void']
        elif re.search(r'\brefunded\b', low): rows = [r for r in rows if str(r.get('status','')).lower() == 'refunded']
        return len(rows)
    # Quantity-based questions / best-selling product.
    if re.search(r'\b(quantity|units|items sold|best[- ]selling|top[- ]selling|most sold)\b', low):
        paid = [r for r in rows if r.get('status') == 'paid']
        if re.search(r'\b(best[- ]selling|top[- ]selling|most sold)\b', low):
            agg = {}
            for r in paid: agg[r.get('product','')] = agg.get(r.get('product',''), 0) + int(r.get('qty',0) or 0)
            if not agg: return ''
            return sorted(agg.items(), key=lambda x: (-x[1], x[0]))[0][0]
        return sum(int(r.get('qty',0) or 0) for r in paid)
    # If no clear aggregation was found, provide a deterministic count rather than a fabricated answer.
    return len(rows)

@app.route('/', methods=['GET', 'POST'])
def root():
    if request.method == 'GET':
        return jsonify({'service':'Acme Appliances Ledger Agent','ready':True,'orders_loaded':len(orders),'usage':'POST JSON {"question":"..."}'})
    data = request.get_json(silent=True) or {}
    q = data.get('question')
    if not isinstance(q, str) or not q.strip():
        return jsonify({'error':'Expected JSON body with a non-empty question string'}), 400
    try:
        return jsonify({'answer': answer(q)})
    except Exception:
        app.logger.exception('Could not answer question')
        return jsonify({'error':'Could not process question'}), 500

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'ok':True,'orders_loaded':len(orders)})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
