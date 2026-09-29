import { createBrowserRouter, Navigate, Outlet } from "react-router";
import { LoginPage } from "../features/auth/LoginPage";
import { SetupPage } from "../features/auth/SetupPage";
import { ConfigEditorPage } from "../features/configure/ConfigEditorPage";
import { ConfigureListPage } from "../features/configure/ConfigureListPage";
import { ImportPage } from "../features/import/ImportPage";
import { PartsPage } from "../features/parts/PartsPage";
import { PrintLabelsPage } from "../features/print/PrintLabelsPage";
import { SettingsPage } from "../features/settings/SettingsPage";
import { RequireAuth, SessionWatcher } from "./auth";
import { Shell } from "./Shell";

function Root() {
  return (
    <>
      <SessionWatcher />
      <Outlet />
    </>
  );
}

function AdminOnly() {
  return (
    <RequireAuth role="admin">
      <Outlet />
    </RequireAuth>
  );
}

export const router = createBrowserRouter([
  {
    element: <Root />,
    children: [
      { path: "/login", element: <LoginPage /> },
      { path: "/setup", element: <SetupPage /> },
      {
        element: (
          <RequireAuth>
            <Shell />
          </RequireAuth>
        ),
        children: [
          { path: "/", element: <Navigate to="/print" replace /> },
          { path: "/print", element: <PrintLabelsPage /> },
          { path: "/parts", element: <PartsPage /> },
          {
            element: <AdminOnly />,
            children: [
              { path: "/parts/import", element: <ImportPage /> },
              { path: "/configure", element: <ConfigureListPage /> },
              { path: "/configure/default", element: <ConfigEditorPage /> },
              { path: "/configure/part/:partId", element: <ConfigEditorPage /> },
              { path: "/settings", element: <Navigate to="/settings/general" replace /> },
              { path: "/settings/:tab", element: <SettingsPage /> },
            ],
          },
          { path: "*", element: <Navigate to="/print" replace /> },
        ],
      },
    ],
  },
]);
