import { useState, useCallback, useEffect, useRef } from "react";
import type { SignalEvent } from "../types";

export interface Toast {
  id: string;
  signal: SignalEvent;
  repoName?: string;
  createdAt: number;
}

export function useToast() {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const timersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

  const addToast = useCallback((signal: SignalEvent, repoName?: string) => {
    const id = crypto.randomUUID();
    const newToast: Toast = { id, signal, repoName, createdAt: Date.now() };

    setToasts((prev) => [newToast, ...prev].slice(0, 5)); // max 5 toasts

    // Auto-dismiss after 6 s
    const timer = setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
      timersRef.current.delete(id);
    }, 6000);
    timersRef.current.set(id, timer);

    return id;
  }, []);

  const dismiss = useCallback((id: string) => {
    const timer = timersRef.current.get(id);
    if (timer) {
      clearTimeout(timer);
      timersRef.current.delete(id);
    }
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    const timers = timersRef.current;
    return () => {
      timers.forEach((timer) => clearTimeout(timer));
    };
  }, []);

  return { toasts, addToast, dismiss };
}
