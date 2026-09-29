import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router";
import { PageTitleProvider } from "./app/page";
import { router } from "./app/router";
import { ToastProvider } from "./components/Toast";
import { ApiError } from "./lib/api";
import "./styles/index.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (count, err) => !(err instanceof ApiError && err.status < 500) && count < 2,
      refetchOnWindowFocus: false,
    },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <PageTitleProvider>
          <RouterProvider router={router} />
        </PageTitleProvider>
      </ToastProvider>
    </QueryClientProvider>
  </StrictMode>,
);
