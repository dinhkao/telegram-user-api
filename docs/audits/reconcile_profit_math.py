"""Đối chiếu chỉ đọc: snapshot SQLite trong RAM, công thức độc lập từ JSON.
Baseline được ghim vào commit trước đợt sửa 10/09/2026. Nếu dữ liệu thật có phiếu nhập lại kho, dừng để đối chiếu vốn
riêng (bộ regression synthetic đã kiểm tra nhánh đó).
"""
import sys, sqlite3, json, os, subprocess, types, importlib.util, time
from pathlib import Path
from decimal import Decimal
from datetime import datetime, timezone, timedelta
ROOT = Path(__file__).resolve().parents[2]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
from dotenv import dotenv_values
from profit_dashboard.compute import dashboard_data, product_detail_data, customers_data
from profit_dashboard.queries import orders_feed, _created_vn
cfg=dotenv_values('.env')
path=Path(os.path.expanduser(cfg.get('SHARED_DB_PATH') or '~/letrang-db/app.db')).resolve()
source=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True);source.execute('PRAGMA query_only=ON')
conn=sqlite3.connect(':memory:');source.backup(conn);source.close();conn.row_factory=sqlite3.Row
conn.execute('PRAGMA query_only=ON')
st= json.loads(Path(os.path.expanduser(cfg.get('PROFIT_SETTINGS_FILE') or '~/letrang-db/profit_settings.json')).read_text())
# Code trước sửa toán được chạy trên CÙNG snapshot RAM.
legacy=types.ModuleType('product_store.legacy_profit');legacy.__package__='product_store'
exec(subprocess.check_output(['git','show','21a3b8b8140b87c6db13541304a6237c02b9594a:product_store/profit.py'],text=True),legacy.__dict__)
old=types.ModuleType('profit_dashboard.legacy_compute');old.__package__='profit_dashboard'
exec(subprocess.check_output(['git','show','21a3b8b8140b87c6db13541304a6237c02b9594a:profit_dashboard/compute.py'],text=True),old.__dict__)
old.calculate_order_profit=legacy.calculate_order_profit
out={'baseline_commit': '21a3b8b8140b87c6db13541304a6237c02b9594a', 'snapshot_at':datetime.now(timezone(timedelta(hours=7))).isoformat(),'periods':[]}
for since in ['2026-09-01','2026-08-12','2026-01-01']:
 until='2026-09-10';start=time.monotonic()
 before=old.dashboard_data(conn,since,until,st['yearly_loan_payment'],st['monthly_weights'])['summary']
 d=dashboard_data(conn,since,until,st['yearly_loan_payment'],st['monthly_weights']);s=d['summary']
 # Phép tính độc lập từ JSON: không gọi calculate_order_profit, scan_orders.
 expected={'revenue':0,'cost':0,'profit':0,'orders':0,'vat':0,'returns_revenue':0,'missing_cost_revenue':0,'customer_total':0}
 for row in conn.execute('SELECT thread_id,json FROM orders WHERE deleted_at IS NULL AND json IS NOT NULL'):
  order=json.loads(row['json']);day,_=_created_vn(order.get('created'))
  if not day or not since<=day<=until:continue
  invoice=order.get('invoice') or order.get('invoice_items') or []
  if not invoice:continue
  expected['orders']+=1
  goods=cost=known=0
  for i in invoice:
   qty=Decimal(str(i.get('sl') if i.get('sl') not in (None,'') else i.get('quantity',0)).replace(',','.'))
   rev=round(qty*Decimal(str(i.get('price') or 0)));goods+=rev
   cp=i.get('cost_price');has=cp is not None and (Decimal(str(cp))>0 or (Decimal(str(cp))==0 and i.get('cost_confirmed') is True)) and i.get('cost_source')!='backfill_current'
   if has:
    c=round(qty*Decimal(str(cp)));cost+=c;known+=rev-c
   else:expected['missing_cost_revenue']+=rev
  vat=round(Decimal(str(order.get('vat') or 0)));fee=round(Decimal(str(order.get('pvc') or 0)))-round(Decimal(str(order.get('discount') or 0)))
  expected['revenue']+=goods+fee;expected['cost']+=cost;expected['profit']+=known+fee+vat-round(Decimal(str(order.get('shipping_cost') or 0)));expected['vat']+=vat
  expected['customer_total']+=goods+fee+vat
 seen=set();returns=[]
 for row in conn.execute('SELECT * FROM return_slips WHERE deleted_at IS NULL AND kv_invoice_id IS NOT NULL ORDER BY id'):
  if row['kv_invoice_id'] in seen:continue
  seen.add(row['kv_invoice_id']);day,_=_created_vn(row['created_at'])
  if not day or not since<=day<=until:continue
  amount=round(row['total']);expected['revenue']-=amount;expected['customer_total']-=amount;expected['profit']-=amount;expected['returns_revenue']+=amount
  result=json.loads(row['goods_result'] or '{}')
  # Live snapshot: chỉ có phiếu hủy hoặc chưa xử lý; nếu phát sinh nhập kho thì
  # dừng đối chiếu đơn giản này, buộc kiểm tra đối ứng vốn riêng.
  assert not result.get('restocked_existing') and not result.get('restocked_new')
  returns.append({'id':row['id'],'amount':amount,'goods_pending':not bool(result)})
 checks={k:s[k]-v for k,v in expected.items() if k!='vat'};checks['vat']=s['fees']['vat']-expected['vat']
 assert all(v==0 for v in checks.values()), checks
 chart={k:sum(x[k] for x in d['chart'])-s[k] for k in ['revenue','cost','profit','loan','real_profit','orders','returns']}
 assert all(v==0 for v in chart.values()),chart
 cust=customers_data(conn,since,until)['totals'];assert all(cust[k]==s[k] for k in ['revenue','cost','profit','orders','returns'])
 assert not d['coverage'].get('invalid_orders') and not d['coverage'].get('invalid_returns'),d['coverage']
 out['periods'].append({'since':since,'until':until,'before':{k:before[k] for k in ['orders','revenue','cost','profit','real_profit']},'after':s,'coverage':d['coverage'],'independent_differences':checks,'chart_differences':chart,'returns':returns,'elapsed_seconds':round(time.monotonic()-start,2)})
pd=product_detail_data(conn,'K2NV120','2026-09-07','2026-09-07');out['duplicate_product_check']={'reported_orders':pd['totals']['orders'],'distinct_orders':len({o['thread_id'] for o in pd['orders'] if o['kind']=='sale'})}
assert out['duplicate_product_check']['reported_orders']==out['duplicate_product_check']['distinct_orders']
f=dashboard_data(conn,'2026-09-01','2026-09-10',st['yearly_loan_payment'],st['monthly_weights'],filter_product='K2NV120')['summary'];assert f['real_profit'] is None
out['filtered_loan']={k:f[k] for k in ['profit','loan','real_profit','company_loan']}
Path('docs/audits/profit_math_vat_confirmed_2026-09-10.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
print(json.dumps({'snapshot_at':out['snapshot_at'],'periods':[{k:p[k] for k in ['since','before','coverage','independent_differences','chart_differences','elapsed_seconds']}|{'after':{k:p['after'][k] for k in ['orders','returns','revenue','profit','real_profit','missing_cost_orders','missing_cost_returns','missing_cost_revenue']}} for p in out['periods']],'duplicate_product_check':out['duplicate_product_check'],'filtered_loan':out['filtered_loan']},ensure_ascii=False,indent=2))
