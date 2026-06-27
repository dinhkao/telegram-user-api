import { SectionCard, Row } from './order-detail-shared';
import { TASK_LABELS, TASKS } from './order-detail-utils';

export function OrderDetailTasks({ tasks, showName }: { tasks: Record<string, any>; showName: (id: any) => string }) {
  return (
    <SectionCard title="Task Status">
      {TASKS.map(tt => {
        const st = tasks[tt];
        const done = st && st.done;
        return (
          <Row key={tt} label={TASK_LABELS[tt]}>
            {done ? <span className="text-emerald-600">✅ Done{st.skip ? ' (skipped)' : ''}{st.note ? ' — ' + st.note : ''}{st.by ? ' — ' + showName(st.by) : ''}</span> : <span className="text-muted-foreground">❌ Not done</span>}
          </Row>
        );
      })}
    </SectionCard>
  );
}
