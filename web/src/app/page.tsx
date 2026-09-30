import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

const PRODUCT = "Novo Smart Labels";

interface PageCtx {
  title: string;
  setTitle: (t: string) => void;
}

const Ctx = createContext<PageCtx>({ title: "", setTitle: () => undefined });

export function PageTitleProvider({ children }: { children: ReactNode }) {
  const [title, setTitle] = useState("");
  return <Ctx.Provider value={{ title, setTitle }}>{children}</Ctx.Provider>;
}

/** Sets the top-bar H1 and the browser tab title "{Page} · Novo Smart Labels" (11.6). */
export function usePage(title: string): void {
  const { setTitle } = useContext(Ctx);
  useEffect(() => {
    setTitle(title);
    document.title = `${title} · ${PRODUCT}`;
  }, [title, setTitle]);
}

export function usePageTitle(): string {
  return useContext(Ctx).title;
}

export function useDocumentTitle(title: string): void {
  useEffect(() => {
    document.title = `${title} · ${PRODUCT}`;
  }, [title]);
}
