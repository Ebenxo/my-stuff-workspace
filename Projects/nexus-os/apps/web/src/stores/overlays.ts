import { create } from "zustand";

/** App-wide overlays opened from anywhere (shortcuts, the top bar, the command line). Not persisted. */
interface OverlayState {
  palette: boolean;
  shortcuts: boolean;
  setPalette: (open: boolean) => void;
  setShortcuts: (open: boolean) => void;
}

export const useOverlays = create<OverlayState>()((set) => ({
  palette: false,
  shortcuts: false,
  setPalette: (palette) => set({ palette, shortcuts: false }),
  setShortcuts: (shortcuts) => set({ shortcuts, palette: false }),
}));
