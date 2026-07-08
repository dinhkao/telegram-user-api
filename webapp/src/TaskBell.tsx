// Icon VIỆC trên app bar (cạnh chuông): badge = số việc CHƯA XONG được giao cho
// user hiện tại. Bấm → #/viec (lọc Của tôi). Data: /api/tasks?counts=1;
// realtime tasks_changed → tải lại. Nối: api, realtime, ui/Icon.
import { useEffect, useState } from "preact/hooks";
import { currentUser, getJSON } from "./api";
import { onRealtime } from "./realtime";
import { Icon } from "./ui/Icon";

export function TaskBell() {
  const [mine, setMine] = useState(0);
  const load = () =>
    getJSON(`/api/tasks?counts=1&me=${encodeURIComponent(currentUser()?.username || "")}`, { cache: false })
      .then((d) => setMine(d.counts?.mine || 0))
      .catch(() => {});
  useEffect(() => {
    load();
    let t: any;
    const off = onRealtime((e) => {
      if (e.type === "tasks_changed") { clearTimeout(t); t = setTimeout(load, 500); }
    });
    return () => { off(); clearTimeout(t); };
  }, []);

  return (
    <a class="icon-btn task-bell" href="#/viec?filter=mine" title="Việc của tôi">
      <Icon name="check" size={19} />
      {mine > 0 && <span class="notif-badge tb-badge">{mine > 9 ? "9+" : mine}</span>}
    </a>
  );
}
