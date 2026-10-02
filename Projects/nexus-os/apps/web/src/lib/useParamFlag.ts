import { useCallback, useState } from "react";
import { useSearchParams } from "react-router";

/**
 * A yes/no UI state that a link can also switch on (``?new=1``), e.g. from the command palette.
 * Closing clears the parameter, so going back does not reopen it.
 */
export function useParamFlag(name: string): [boolean, (open: boolean) => void] {
  const [params, setParams] = useSearchParams();
  const [local, setLocal] = useState(false);
  const fromUrl = params.get(name) === "1";
  const set = useCallback(
    (open: boolean) => {
      setLocal(open);
      if (!open && fromUrl) {
        setParams(
          (prev) => {
            const next = new URLSearchParams(prev);
            next.delete(name);
            return next;
          },
          { replace: true },
        );
      }
    },
    [fromUrl, name, setParams],
  );
  return [local || fromUrl, set];
}
