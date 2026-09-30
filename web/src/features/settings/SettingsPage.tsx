import { Building2, Hash, ListPlus, Printer, Ruler, Users, type LucideIcon } from "lucide-react";
import { NavLink, Navigate, useParams } from "react-router";
import { Page } from "../../app/Shell";
import { usePage } from "../../app/page";
import { FieldsTab } from "./FieldsTab";
import { GeneralTab, SerialTab } from "./GeneralTabs";
import { PrintersTab } from "./PrintersTab";
import { SizesTab } from "./SizesTab";
import { UsersTab } from "./UsersTab";

const TABS: { slug: string; label: string; icon: LucideIcon; hint: string; el: React.ReactNode }[] = [
  { slug: "general", label: "General", icon: Building2, hint: "Your company name", el: <GeneralTab /> },
  { slug: "serial-numbers", label: "Serial numbers", icon: Hash, hint: "Format and the next number", el: <SerialTab /> },
  { slug: "label-sizes", label: "Label sizes", icon: Ruler, hint: "The label rolls you use", el: <SizesTab /> },
  { slug: "custom-fields", label: "Custom fields", icon: ListPlus, hint: "Extra details stored on parts", el: <FieldsTab /> },
  { slug: "printers", label: "Printers", icon: Printer, hint: "The printer and its print agent", el: <PrintersTab /> },
  { slug: "users", label: "Users", icon: Users, hint: "Who can sign in, and their role", el: <UsersTab /> },
];

/** 12.13 Settings: vertical tabs on the left (200 px). */
export function SettingsPage() {
  usePage("Settings");
  const { tab } = useParams();
  const current = TABS.find((t) => t.slug === tab);
  if (!current) return <Navigate to="/settings/general" replace />;
  return (
    <Page>
      <div className="flex gap-8">
        <nav aria-label="Settings" className="flex w-[260px] shrink-0 flex-col gap-1 self-start rounded-[12px] border border-border bg-surface p-2 shadow-card">
          {TABS.map((t) => (
            <NavLink
              key={t.slug}
              to={`/settings/${t.slug}`}
              className={({ isActive }) =>
                `group flex items-center gap-3 rounded-[8px] px-3 py-2.5 transition-colors duration-150 ${isActive ? "bg-primary text-white shadow-card" : "text-text hover:bg-hover-fill"}`
              }
            >
              {({ isActive }) => (
                <>
                  <span className={`inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-[8px] ${isActive ? "bg-white/15 text-white" : "bg-primary-subtle text-primary"}`}>
                    <t.icon size={16} strokeWidth={1.75} aria-hidden />
                  </span>
                  <span className="flex min-w-0 flex-col">
                    <span className="t-body-strong">{t.label}</span>
                    <span className={`truncate t-caption ${isActive ? "text-white/80" : "text-text-muted"}`}>{t.hint}</span>
                  </span>
                </>
              )}
            </NavLink>
          ))}
        </nav>
        <section className="min-w-0 flex-1" aria-label={current.label}>
          <div className="mb-5 flex items-center gap-4">
            <span className="inline-flex h-11 w-11 items-center justify-center rounded-[10px] bg-primary text-white shadow-card">
              <current.icon size={20} strokeWidth={1.75} aria-hidden />
            </span>
            <div className="flex flex-col">
              <h2 className="t-h2 text-text">{current.label}</h2>
              <p className="t-small text-text-muted">{current.hint}</p>
            </div>
          </div>
          {current.el}
        </section>
      </div>
    </Page>
  );
}
