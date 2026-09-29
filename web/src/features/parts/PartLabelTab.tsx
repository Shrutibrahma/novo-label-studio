import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router";
import { useIsAdmin } from "../../app/auth";
import { Button } from "../../components/Button";
import { LabelPreview, usePreview } from "../../components/LabelPreview";
import { useToast } from "../../components/Toast";
import { api, ApiError } from "../../lib/api";
import { formatDate } from "../../lib/format";
import { qk } from "../../lib/queries";
import type { PartDetail } from "../../lib/parts";

/** 12.8 "Label" tab: effective config, a static preview, last print, customize / use default. */
export function PartLabelTab({ part }: { part: PartDetail }) {
  const isAdmin = useIsAdmin();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const toast = useToast();
  const preview = usePreview({ part_id: part.id, config_id: part.config.id }, 0);
  const useDefault = useMutation({
    mutationFn: () => api(`/parts/${part.id}/config`, { method: "DELETE" }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: qk.part(part.id) });
      void qc.invalidateQueries({ queryKey: ["parts"] });
      void qc.invalidateQueries({ queryKey: qk.configs });
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : String(e)),
  });
  return (
    <div className="flex flex-col gap-4 p-6">
      <p className="t-body-strong text-text">{part.has_override ? `Custom label for this part · v${part.config.version}` : "Uses the default label"}</p>
      <LabelPreview result={preview.data} loading={preview.isFetching} padding={12} shrink showActualSizeToggle={false} />
      <p className="t-body text-text-secondary">{part.last_printed_at ? `Last printed ${formatDate(part.last_printed_at)}` : "Never printed"}</p>
      {isAdmin && (
        <div className="flex gap-2">
          <Button onClick={() => navigate(`/configure/part/${part.id}`)}>Customize for this part</Button>
          {part.has_override && (
            <Button variant="ghost" loading={useDefault.isPending} onClick={() => useDefault.mutate()}>
              Use default label
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
