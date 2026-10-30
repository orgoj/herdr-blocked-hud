---
type: knowledge
summary: "Architektura a implementace stavového plovoucího HUD okna pro Herdr v Linuxu - automatické zobrazení v popředí při zablokování agenta, pípnutí, click-to-focus a automatické skrytí."
tags: [herdr, hud, linux, x11, python, openbox, lxqt, agent-tool]
status: active
updated: 2026-10-30
related:
  - "[[ogulcancelik-herdr]]"
  - "[[quinnjr-herdr-notifications]]"
  - "[[linux-desktop-notification-daemons-comparison]]"
---

# Stavový plovoucí HUD pro blokované agenty v Herdr

## Problém klasických systémových notifikací u kódovacích agentů

Běžné systémové desktopové notifikace (toasty přes D-Bus `org.freedesktop.Notifications`) jsou navrženy pro pasivní zprávy, nikoli pro řízení stavu běžících agentů:
1. **Časový limit je nežádoucí:** Pokud notifikace po 5-10 sekundách zmizí, vývojář snadno přehlédne, že agent čeká na potvrzení příkazu, a práce stojí.
2. **Trvalá notifikace (timeout = 0) překáží:** Pokud se notifikace nastaví bez timeoutu, zůstává viset na obrazovce i poté, co uživatel panel v terminálu přepnul a agenta odblokoval (notifikační démon neví, že stav pominul).
3. **Chybějící reaktivita na stav:** Vývojář nepotřebuje notifikaci v historii, ale **stavový indikátor** – malý plovoucí panel v popředí (always-on-top), který existuje pouze tehdy, když alespoň jeden agent vyžaduje zásah, a jakmile agent začne pracovat, sám zmizí.

---

## Požadované vlastnosti řešení

- **Zámek v horní vrstvě (Always on Top):** Panel je trvale nad všemi ostatními okny (X11 `_NET_WM_STATE_ABOVE`).
- **Zvuková signalizace:** Při přechodu kteréhokoli agenta do stavu `blocked` panel pípne (systémový bell nebo `paplay`).
- **Čistě stavové zobrazení:** Zobrazuje pouze aktuálně blokované panely (`workspace · tab · agent`).
- **Click-to-focus:** Kliknutí na položku:
  1. Zavolá `herdr agent focus <pane_id>` (přepne panel v multiplexeru).
  2. Aktivuje a vynese hostitelské okno terminálu do popředí pomocí `wmctrl` / `xdotool`.
- **Automatické skrytí:** Jakmile uživatel agenta odblokuje a stav přejde na `working`, panel položku odstraní. Pokud je seznam prázdný, celé okno se automaticky skryje (`withdraw`).

---

## Implementace: Lehký Python / Tkinter HUD (`herdr-blocked-hud`)

Skript využívá Python 3 s vestavěnou knihovnou Tkinter (nativní součást desktopů, bez těžkých závislostí) a komunikuje s CLI / socket API Herdr.

### Kód skriptu (`~/.local/bin/herdr-blocked-hud`)

```python
#!/usr/bin/env python3
"""
herdr-blocked-hud: Plovoucí always-on-top panel pro zablokované agenty v Herdr.
Zobrazí se pouze tehdy, když alespoň jeden agent čeká na vstup.
Při příchodu pípne. Po kliknutí aktivuje okno terminálu a panel v Herdr.
Jakmile žádný agent nečeká, sám zmizí.
"""

import json
import subprocess
import sys
import tkinter as tk
from tkinter import font

CHECK_INTERVAL_MS = 1000  # Kontrola stavu každou sekundu


class HerdrBlockedHud:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Herdr Blocked Agents")
        
        # Okno bez dekorací (borderless), vždy nahoře a přes všechny plochy
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg="#1e1e2e")

        self.last_blocked_ids = set()
        self.buttons = {}

        # Kontejner pro tlačítka
        self.frame = tk.Frame(self.root, bg="#1e1e2e", padx=6, pady=6)
        self.frame.pack(fill=tk.BOTH, expand=True)

        self.header = tk.Label(
            self.frame,
            text="⚠️ Čekající agenti",
            bg="#1e1e2e",
            fg="#fab387",
            font=("Sans", 10, "bold"),
            anchor="w",
        )
        self.header.pack(fill=tk.X, pady=(0, 4))

        # Začínáme skrytí
        self.is_visible = False
        self.root.withdraw()

        # Spuštění periodické smyčky
        self.poll_herdr_status()

    def beep(self):
        """Pípnutí při novém zablokovaném agentovi."""
        try:
            # Systémové pípnutí nebo přehrání zvuku
            print("\a", end="", flush=True)
            subprocess.run(
                ["paplay", "/usr/share/sounds/freedesktop/stereo/dialog-warning.oga"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=0.5,
            )
        except Exception:
            pass

    def get_blocked_panes(self):
        """Získání seznamu blokovaných panelů z Herdr."""
        try:
            res = subprocess.run(
                ["herdr", "pane", "list", "--json"],
                capture_output=True,
                text=True,
                timeout=1.5,
            )
            if res.returncode != 0:
                return []
            data = json.loads(res.stdout)
            # Extrakce panelů
            panes = data.get("result", {}).get("panes", []) if isinstance(data, dict) else []
            blocked = []
            for p in panes:
                if p.get("agent_status") == "blocked":
                    blocked.append(p)
            return blocked
        except Exception:
            return []

    def focus_pane(self, pane_id: str):
        """Přepnutí panelu v Herdr a vynesení okna terminálu."""
        # 1. Přepnutí fokus uvnitř Herdr
        subprocess.run(["herdr", "agent", "focus", pane_id], check=False)

        # 2. Vynesení okna terminálu do popředí (X11)
        # Hledáme okno obsahující "herdr" nebo terminálový proces
        try:
            # Pokus aktivovat přes wmctrl
            subprocess.run(["wmctrl", "-a", "herdr"], check=False)
        except Exception:
            pass

    def update_ui(self, blocked_panes):
        current_ids = {p.get("pane_id") for p in blocked_panes}

        # Pípnutí při novém zablokovaném agentovi
        new_ids = current_ids - self.last_blocked_ids
        if new_ids:
            self.beep()

        # Pokud nic nečeká, okno skryjeme
        if not current_ids:
            if self.is_visible:
                self.root.withdraw()
                self.is_visible = False
            self.last_blocked_ids = set()
            # Vyčištění tlačítek
            for btn in self.buttons.values():
                btn.destroy()
            self.buttons.clear()
            return

        # Aktualizace tlačítek pro panely
        for pane in blocked_panes:
            pid = pane.get("pane_id")
            title = pane.get("title") or pane.get("agent") or pid
            label_text = f"▶ {title} ({pid})"

            if pid not in self.buttons:
                btn = tk.Button(
                    self.frame,
                    text=label_text,
                    bg="#313244",
                    fg="#cdd6f4",
                    activebackground="#f38ba8",
                    activeforeground="#11111b",
                    relief=tk.FLAT,
                    padx=8,
                    pady=4,
                    anchor="w",
                    command=lambda p=pid: self.focus_pane(p),
                )
                btn.pack(fill=tk.X, pady=2)
                self.buttons[pid] = btn
            else:
                self.buttons[pid].configure(text=label_text)

        # Odstranění tlačítek pro již odblokované panely
        removed_ids = set(self.buttons.keys()) - current_ids
        for rid in removed_ids:
            self.buttons[rid].destroy()
            del self.buttons[rid]

        # Zobrazení okna pokud bylo skryté
        if not self.is_visible:
            # Umístění v pravém horním rohu obrazovky
            self.root.update_idletasks()
            w = 260
            h = self.frame.winfo_reqheight()
            screen_w = self.root.winfo_screenwidth()
            x = screen_w - w - 24
            y = 36
            self.root.geometry(f"{w}x{h}+{x}+{y}")
            self.root.deiconify()
            self.root.attributes("-topmost", True)
            self.is_visible = True

        self.last_blocked_ids = current_ids

    def poll_herdr_status(self):
        blocked = self.get_blocked_panes()
        self.update_ui(blocked)
        self.root.after(CHECK_INTERVAL_MS, self.poll_herdr_status)


def main():
    root = tk.Tk()
    app = HerdrBlockedHud(root)
    root.mainloop()


if __name__ == "__main__":
    main()
```

---

## Výhody tohoto přístupu oproti systémovým notifikacím

1. **Žádné nechtěné mizení:** Panel nezmizí po 10 sekundách. Zůstává na očích přesně tak dlouho, dokud agent skutečně čeká na uživatele.
2. **Okamžité zmizení po odblokování:** Jakmile v Herdr odpovíte nebo schválíte operaci a agent přejde do `working`, panel při příštím cyklu (do 1 s) automaticky položku smaže a okno se zatáhne.
3. **Zvuková vazba (Pípnutí):** Vývojář nemusí sledovat obrazovku; jakmile agent narazí na překážku, panel pípne a objeví se v popředí.
4. **Nezávislost na notifikačním démonu:** Není nutné řešit chyby v `lxqt-notificationd`, nefunkční D-Bus akce ani nastavení timeoutů v desktopovém prostředí.

## Související stránky

- [[ogulcancelik-herdr]] — Terminálový multiplexer pro kódovací agenty
- [[quinnjr-herdr-notifications]] — Plugin herdr-notifications přes D-Bus
- [[linux-desktop-notification-daemons-comparison]] — Srovnání notifikačních démonů pro Linux
