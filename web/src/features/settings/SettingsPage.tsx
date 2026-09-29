import { NavLink, Navigate, useParams } from "react-router";
import { Page } from "../../app/Shell";
import { usePage } from "../../app/page";
import { FieldsTab } from "./FieldsTab";
import { GeneralTab, SerialTab } from "./GeneralTabs";
import { PrintersTab } from "./PrintersTab";
import { SizesTab } from "./SizesTab";
import { UsersTab } from "./UsersTab";

const TABS = [
  { slug: "general", label: "General", el: <GeneralTab /> },
  { slug: "serial-numbers", label: "Serial numbers", el: <SerialTab /> },
  { slug: "label-sizes", label: "Label sizes", el: <SizesTab /> },
  { slug: "custom-fields", label: "Custom fields", el: <FieldsTab /> },
  { slug: "printers", label: "Printers", el: <PrintersTab /> },
  { slug: "users", label: "Users", el: <UsersTab /> },
] as const;

/** 12.13 Settings: vertical tabs on the left (200 px). */
export function SettingsPage() {
  usePage("Settings");
  const { tab } = useParams();
  const current = TABS.find((t) => t.slug === tab);
  if (!current) return <Navigate to="/settings/general" replace />;
  return (
    <Page>
      <div className="flex gap-8">
        <nav aria-label="Settings" className="flex w-[200px] shrink-0 flex-col gap-0.5">
          {TABS.map((t) => (
            <NavLink
              key={t.slug}
              to={`/settings/${t.slug}`}
              className={({ isActive }) =>
                `rounded-[6px] px-3 py-2 t-body-strong transition-colors duration-150 ${isActive ? "bg-primary-subtle text-primary" : "text-text-secondary hover:bg-hover-fill"}`
              }
            >
              {t.label}
            </NavLink>
          ))}
        </nav>
        <section className="min-w-0 flex-1" aria-label={current.label}>
          <h2 className="mb-4 t-h2 text-text">{current.label}</h2>
          {current.el}
        </section>
      </div>
    </Page>
  );
}
