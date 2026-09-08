// Chi tiết 1 BẢN DỰ BÁO HÀNG HOÁ (#/du-bao/:id) — thẻ tóm tắt hôm nay/tuần này,
// nhận định AI (markdown), bảng theo nhóm hàng cho hôm nay + tuần, 7 ngày qua và
// sự kiện sắp tới. Data: getForecast (server TỰ đánh dấu đã xem khi gọi).
// Realtime forecast_changed → tải lại.
import { useEffect, useState } from "preact/hooks";
import { getForecast, type ForecastFull } from "../api";
import { renderMarkdown } from "../detail/markdown";
import { fmtDateTimeVN } from "../format";
import { onRealtime } from "../realtime";
import { Icon } from "../ui/Icon";
import { PageHead } from "../ui/PageHead";
import { EmptyState, ErrorState, Loading } from "../ui/states";
import { fmtN } from "./ForecastList";

/** "2026-09-08" → "8/9" */
function dm(ymd: string): string {
  const p = String(ymd || "").split("-");
  return p.length === 3 ? `${Number(p[2])}/${Number(p[1])}` : ymd || "";
}

/** Ô "Nhóm": mã nhóm đậm + tên đầy đủ chữ nhỏ bên dưới. */
function FamCell({ fam, name }: { fam: string; name: string }) {
  return (
    <>
      <b>{fam}</b>
      {name && name !== fam ? <div class="muted small">{name}</div> : null}
    </>
  );
}

/** Bảng HÔM NAY theo nhóm — dòng nhỏ (fc < 10) gập lại cho gọn màn điện thoại. */
function DayTable({ rows }: { rows: ForecastFull["data"]["day"]["rows"] }) {
  const big = rows.filter((r) => r.fc >= 10);
  const small = rows.filter((r) => r.fc < 10);
  const body = (rs: typeof rows) => rs.map((r) => (
    <tr key={r.fam + r.name}>
      <td><FamCell fam={r.fam} name={r.name} /></td>
      <td class="muted">{r.unit}</td>
      <td class="num">{fmtN(r.fc)}</td>
      <td class="num"><b>{fmtN(r.hi)}</b></td>
    </tr>
  ));
  const head = (
    <thead><tr><th>Nhóm</th><th>ĐVT</th><th class="num">Dự báo</th><th class="num">Chuẩn bị</th></tr></thead>
  );
  return (
    <>
      <div class="fc-tbl-wrap">
        <table class="fc-tbl">
          {head}
          <tbody>{body(big)}</tbody>
        </table>
      </div>
      {small.length > 0 && (
        <details class="fc-details">
          <summary>{small.length} nhóm lượng nhỏ (dưới 10)</summary>
          <div class="fc-tbl-wrap">
            <table class="fc-tbl">
              {head}
              <tbody>{body(small)}</tbody>
            </table>
          </div>
        </details>
      )}
    </>
  );
}

function WeekTable({ rows }: { rows: ForecastFull["data"]["week"]["rows"] }) {
  return (
    <div class="fc-tbl-wrap">
      <table class="fc-tbl">
        <thead>
          <tr>
            <th>Nhóm</th><th class="num">Dự báo</th><th class="num">Đã bán</th>
            <th class="num">Còn cần</th><th class="num">Chuẩn bị</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.fam + r.name}>
              <td><FamCell fam={r.fam} name={r.name} /></td>
              <td class="num">{fmtN(r.fc)}</td>
              <td class="num muted">{fmtN(r.sofar)}</td>
              <td class="num">{fmtN(r.remain)}</td>
              <td class="num"><b>{fmtN(r.hi)}</b></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ForecastDetail({ id }: { id: string }) {
  const [fc, setFc] = useState<ForecastFull | null | undefined>(undefined);
  const [err, setErr] = useState("");

  const load = async () => {
    try { setFc(await getForecast(id)); setErr(""); }
    catch (e: any) { setErr(e?.message || "Lỗi tải bản dự báo"); setFc(null); }
  };
  useEffect(() => { load(); }, [id]);
  useEffect(() => onRealtime((e) => {
    if (e.type === "forecast_changed" || e.type === "resync") load();
  }), [id]);

  if (err && fc === null) return <ErrorState msg={err} onRetry={() => { setErr(""); load(); }} />;
  if (fc === undefined) return <Loading />;
  if (fc === null) return <EmptyState>Không tìm thấy bản dự báo. <a href="#/du-bao">← Dự báo hàng hoá</a></EmptyState>;

  const d = fc.data;
  const y = d.yesterday;
  return (
    <div class="inv-dash fc-detail">
      <PageHead fallback="#/du-bao"
        title={<span><Icon name="chart" size={18} /> {fc.title}</span>}
        sub={`${fc.dow_label} · ${fc.lunar_label}${fc.model ? ` · AI: ${fc.model}` : ""}`} />

      {/* (a) 2 ô tóm tắt */}
      <div class="fc-sumcards">
        <div class="fc-sumcard">
          <span class="fc-num-lbl">Hôm nay</span>
          <b class="fc-big">{fmtN(d.day.total)}</b>
          <span class="muted small">chuẩn bị tới <b>{fmtN(d.day.hi)}</b></span>
        </div>
        <div class="fc-sumcard">
          <span class="fc-num-lbl">Tuần này</span>
          <b class="fc-big">{fmtN(d.week.total)}</b>
          <span class="muted small">
            đã bán {fmtN(d.week.sofar)} · còn {fmtN(d.week.remain)}
            <br />{dm(d.week.from)} → {dm(d.week.to)}
          </span>
        </div>
      </div>

      {/* (f) sự kiện sắp tới */}
      {d.events && d.events.length ? (
        <>
                    <div class="fc-events">
            {d.events.map((ev) => (
              <span class="fc-event" key={ev.name + ev.ymd}>
                <b>{ev.name}</b> · còn {ev.days} ngày <span class="muted small">({dm(ev.ymd)})</span>
              </span>
            ))}
          </div>
        </>
      ) : null}


      {/* (b) nhận định AI */}
      {fc.body_md ? (
        <section class="card fc-md">
          <div class="md-body" dangerouslySetInnerHTML={{ __html: renderMarkdown(fc.body_md) }} />
        </section>
      ) : null}

      {/* Bảng số chi tiết — gập mặc định: phần nhận định ở trên là đủ cho người đọc thường */}
      <details class="fc-details fc-more">
        <summary>Bảng số chi tiết</summary>
      {/* (c) hôm nay theo nhóm */}
      <h3 class="fc-h"><Icon name="box" size={16} /> Hôm nay theo nhóm</h3>
      {d.day.rows.length ? <DayTable rows={d.day.rows} />
        : <EmptyState>Không có nhóm hàng nào cần chuẩn bị hôm nay.</EmptyState>}

      {/* (d) tuần này theo nhóm */}
      <h3 class="fc-h"><Icon name="calendar" size={16} /> Tuần này theo nhóm</h3>
      {d.week.rows.length ? <WeekTable rows={d.week.rows} />
        : <EmptyState>Chưa có số liệu tuần này.</EmptyState>}

      {/* (e) 7 ngày qua + đối chiếu dự báo hôm qua */}
      <h3 class="fc-h"><Icon name="history" size={16} /> 7 ngày qua</h3>
      {y && y.forecast != null ? (
        <div class="fc-yday muted small">
          Hôm qua ({dm(y.ymd)}) dự báo <b>{fmtN(y.forecast)}</b>, thực tế <b>{fmtN(y.total)}</b>.
        </div>
      ) : null}
      <div class="fc-tbl-wrap">
        <table class="fc-tbl">
          <thead><tr><th>Ngày</th><th class="num">Đơn</th><th class="num">Số lượng</th></tr></thead>
          <tbody>
            {(d.last7 || []).map((r) => (
              <tr key={r.ymd}>
                <td>{dm(r.ymd)}</td>
                <td class="num muted">{fmtN(r.orders)}</td>
                <td class="num">{fmtN(r.total)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      </details>

      <p class="muted small fc-foot">Bản dự báo tạo lúc {fmtDateTimeVN(fc.created_at)}.</p>
    </div>
  );
}
