import React from "react";
import ReactDOM from "react-dom/client";
import { HashRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { LazyMotion, MotionConfig, domAnimation } from "motion/react";
import { App } from "@/App";
import { ThemeProvider } from "@/theme/ThemeProvider";
import "@/theme/fonts.css";
import "@/theme/theme.css";
import "@/theme/components.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 15_000,
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <LazyMotion features={domAnimation} strict>
          <MotionConfig reducedMotion="user" transition={{ type: "spring", stiffness: 400, damping: 30 }}>
            <HashRouter>
              <App />
            </HashRouter>
          </MotionConfig>
        </LazyMotion>
      </ThemeProvider>
    </QueryClientProvider>
  </React.StrictMode>,
);
