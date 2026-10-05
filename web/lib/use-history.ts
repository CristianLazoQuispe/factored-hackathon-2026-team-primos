"use client";

import { useCallback, useEffect, useState } from "react";

import {
  type OpenedConversation,
  type PastConversation,
  getConversation,
  getConversations,
  hideConversations,
} from "@/lib/memory";
import { readSession } from "@/lib/session";

// The customer's earlier conversations on the screen. What is loaded belongs to the customer who was
// signed in when it was loaded: if another signs in, the old list is simply not theirs and is ignored,
// so nobody ever sees a previous customer's conversations, however the screens are reused.

// The token as it is, only if it is still good AND it is the token of the customer the screen is for.
// The history is a convenience: unlike the chat it never renews a token and never ends a session. If the
// session belongs to somebody else than the screen thinks, nothing is asked: what came back could be
// stored as the wrong customer's.
function bearer(customerId: string): Record<string, string> | null {
  const current = readSession();
  if (!customerId || !current || current.customer !== customerId || current.expiresAt <= Date.now()) return null;
  return { Authorization: `Bearer ${current.token}` };
}

type Owned<T> = { customer: string; value: T };

export function useHistory(customerId: string, threadId: string) {
  const [listed, setListed] = useState<Owned<PastConversation[] | null> | null>(null);
  const [read, setRead] = useState<Owned<OpenedConversation> | null>(null);
  const [said, setSaid] = useState<Owned<string> | null>(null);
  const [hiding, setHiding] = useState(false);

  // `null`: nothing loaded for this customer, or this deployment keeps no history.
  const history = listed && listed.customer === customerId ? listed.value : null;
  const opened = read && read.customer === customerId ? read.value : null;
  const note = said && said.customer === customerId ? said.value : "";

  const refresh = useCallback(async () => {
    const auth = bearer(customerId);
    if (!auth) return;
    try {
      setListed({ customer: customerId, value: await getConversations(auth) });
    } catch {
      // if it cannot be read it stays as it was
    }
  }, [customerId]);

  useEffect(() => {
    const auth = bearer(customerId);
    if (!auth) return;
    let live = true;
    getConversations(auth)
      .then((found) => {
        if (live) setListed({ customer: customerId, value: found });
      })
      .catch(() => undefined); // see `refresh`
    return () => {
      live = false;
    };
  }, [customerId]);

  const open = useCallback(
    async (id: string) => {
      const auth = bearer(customerId);
      if (!auth) return;
      setSaid(null);
      try {
        const found = await getConversation(auth, id);
        if (found) setRead({ customer: customerId, value: found });
        else setSaid({ customer: customerId, value: "Esa conversación ya no está disponible." });
      } catch (error) {
        setSaid({ customer: customerId, value: (error as Error).message });
      }
    },
    [customerId],
  );

  const back = useCallback(() => setRead(null), []);

  // Hides the earlier conversations, not the one that is open.
  const hide = useCallback(async () => {
    const auth = bearer(customerId);
    if (!auth) return;
    setHiding(true);
    setSaid(null);
    try {
      await hideConversations(auth, threadId);
      setRead(null);
      await refresh();
    } catch (error) {
      setSaid({ customer: customerId, value: (error as Error).message });
    } finally {
      setHiding(false);
    }
  }, [customerId, threadId, refresh]);

  return { history, opened, note, hiding, refresh, open, back, hide };
}
