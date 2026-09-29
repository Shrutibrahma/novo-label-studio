import { CircleCheck } from "lucide-react";
import { useNavigate } from "react-router";
import { Button } from "../../components/Button";
import { Card } from "../../components/Display";
import { thousands } from "../../lib/format";
import type { CommitResult, ImportBatch } from "./types";

/** 12.10 "Done". */
export function DoneStep({ result, batch }: { result: CommitResult | null; batch: ImportBatch }) {
  const navigate = useNavigate();
  const n = result ?? { new: batch.counts.new, updated: batch.counts.updated, marked_inactive: batch.counts.missing, skipped: batch.counts.invalid };
  return (
    <Card className="flex max-w-[560px] flex-col items-center gap-3 text-center">
      <CircleCheck size={40} strokeWidth={1.75} className="text-success" aria-hidden />
      <h2 className="t-h2 text-text">Import complete</h2>
      <p className="t-body text-text-secondary">
        {thousands(n.new)} new · {thousands(n.updated)} updated · {thousands(n.marked_inactive)} marked inactive
      </p>
      {n.skipped > 0 && <p className="t-body text-text-secondary">{thousands(n.skipped)} rows skipped because of errors.</p>}
      <div className="mt-3 flex gap-2">
        <Button variant="secondary" onClick={() => navigate("/parts")}>
          View parts
        </Button>
        <Button onClick={() => navigate("/print?filter=out_of_date")}>Print out-of-date labels</Button>
      </div>
    </Card>
  );
}
