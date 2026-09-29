import { createBrowserRouter, Navigate, Outlet } from "react-router";
import { LoginPage } from "../features/auth/LoginPage";
import { SetupPage } from "../features/auth/SetupPage";
import { PrintLabelsPage } from "../features/print/PrintLabelsPage";
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
          { path: "*", element: <Navigate to="/print" replace /> },
        ],
      },
    ],
  },
]);
