import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, Plus } from "lucide-react";
import { useState } from "react";
import { Button } from "../../components/Button";
import { Badge, Banner } from "../../components/Display";
import { Field, Input, Select } from "../../components/Form";
import { Menu } from "../../components/Menu";
import { Dialog } from "../../components/Overlay";
import { SkeletonRows, Table, Td, Th, Tr } from "../../components/Table";
import { useToast } from "../../components/Toast";
import { api, ApiError } from "../../lib/api";
import { formatDateTime } from "../../lib/format";
import { qk } from "../../lib/queries";
import type { Role, UserRow } from "../../lib/types";

const ROLE_LABEL: Record<Role, string> = { admin: "Admin", operator: "Operator" };
const ROLE_OPTIONS = [
  { value: "operator", label: "Operator" },
  { value: "admin", label: "Admin" },
];

type Edit = { kind: "add" } | { kind: "password"; user: UserRow } | { kind: "role"; user: UserRow };

export function UsersTab() {
  const qc = useQueryClient();
  const toast = useToast();
  const users = useQuery({ queryKey: qk.users, queryFn: () => api<UserRow[]>("/users") });
  const [edit, setEdit] = useState<Edit | null>(null);
  const patch = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Record<string, unknown> }) => api<UserRow>(`/users/${id}`, { method: "PATCH", body }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: qk.users }),
    onError: (e) => toast.error(e instanceof ApiError ? e.message : String(e)),
  });
  return (
    <div className="flex flex-col gap-4">
      <div>
        <Button icon={Plus} onClick={() => setEdit({ kind: "add" })}>
          Add user
        </Button>
      </div>
      {users.error && <Banner tone="danger">{users.error.message}</Banner>}
      <Table>
        <thead>
          <tr>
            <Th>Name</Th>
            <Th>Username</Th>
            <Th>Role</Th>
            <Th>Status</Th>
            <Th>Last login</Th>
            <Th className="w-12">
              <span className="sr-only">Actions</span>
            </Th>
          </tr>
        </thead>
        <tbody>
          {users.isPending ? (
            <SkeletonRows columns={6} />
          ) : (
            (users.data ?? []).map((u) => (
              <Tr key={u.id}>
                <Td className="t-body-strong text-text">{u.display_name}</Td>
                <Td>{u.username}</Td>
                <Td>{ROLE_LABEL[u.role]}</Td>
                <Td>{u.active ? <Badge tone="success">Active</Badge> : <Badge tone="neutral">Inactive</Badge>}</Td>
                <Td>{formatDateTime(u.last_login_at)}</Td>
                <Td>
                  <Menu
                    label={`Actions for ${u.display_name}`}
                    items={[
                      { label: "Reset password", onSelect: () => setEdit({ kind: "password", user: u }) },
                      { label: "Change role", onSelect: () => setEdit({ kind: "role", user: u }) },
                      u.active
                        ? { label: "Deactivate", danger: true, onSelect: () => patch.mutate({ id: u.id, body: { active: false } }) }
                        : { label: "Activate", onSelect: () => patch.mutate({ id: u.id, body: { active: true } }) },
                    ]}
                    trigger={(p) => (
                      <button type="button" {...p} aria-label={`Actions for ${u.display_name}`} className="rounded-[6px] p-1 text-text-secondary hover:bg-hover-fill">
                        <ChevronDown size={16} strokeWidth={1.75} aria-hidden />
                      </button>
                    )}
                  />
                </Td>
              </Tr>
            ))
          )}
        </tbody>
      </Table>
      <UserDialog edit={edit} onClose={() => setEdit(null)} />
    </div>
  );
}

function UserDialog({ edit, onClose }: { edit: Edit | null; onClose: () => void }) {
  const qc = useQueryClient();
  const [form, setForm] = useState({ display_name: "", username: "", role: "operator" as Role, password: "" });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [openedFor, setOpenedFor] = useState<Edit | null>(null);
  if (edit !== openedFor) {
    setOpenedFor(edit);
    setErrors({});
    setForm({ display_name: "", username: "", role: edit?.kind === "role" ? edit.user.role : "operator", password: "" });
  }
  const save = useMutation({
    mutationFn: () => {
      if (!edit) throw new Error("no edit");
      if (edit.kind === "add") return api<UserRow>("/users", { body: form });
      if (edit.kind === "password") return api<UserRow>(`/users/${edit.user.id}`, { method: "PATCH", body: { password: form.password } });
      return api<UserRow>(`/users/${edit.user.id}`, { method: "PATCH", body: { role: form.role } });
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: qk.users });
      onClose();
    },
    onError: (e) => setErrors(e instanceof ApiError ? (Object.keys(e.fields).length ? e.fields : { form: e.message }) : { form: String(e) }),
  });
  const title = edit?.kind === "add" ? "Add user" : edit?.kind === "password" ? "Reset password" : "Change role";
  return (
    <Dialog
      open={edit !== null}
      onClose={onClose}
      title={title}
      subtitle={edit && edit.kind !== "add" ? edit.user.display_name : undefined}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button loading={save.isPending} onClick={() => save.mutate()}>
            {edit?.kind === "add" ? "Add user" : "Save"}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        {edit?.kind === "add" && (
          <>
            <Field label="Display name" htmlFor="u-name" error={errors.display_name}>
              <Input id="u-name" data-autofocus value={form.display_name} error={errors.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} />
            </Field>
            <Field label="Username" htmlFor="u-username" error={errors.username}>
              <Input id="u-username" value={form.username} error={errors.username} onChange={(e) => setForm({ ...form, username: e.target.value })} />
            </Field>
          </>
        )}
        {(edit?.kind === "add" || edit?.kind === "role") && (
          <Field label="Role" htmlFor="u-role">
            <Select id="u-role" value={form.role} options={ROLE_OPTIONS} onChange={(e) => setForm({ ...form, role: e.target.value as Role })} />
          </Field>
        )}
        {(edit?.kind === "add" || edit?.kind === "password") && (
          <Field label={edit.kind === "add" ? "Temporary password" : "Password"} htmlFor="u-pw" error={errors.password} helper="Minimum 12 characters.">
            <Input id="u-pw" type="password" autoComplete="new-password" value={form.password} error={errors.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
          </Field>
        )}
        {errors.form && <p role="alert" className="t-small text-danger">{errors.form}</p>}
      </div>
    </Dialog>
  );
}
