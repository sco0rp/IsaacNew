# iPhone 16 Pro — Shortcuts für S8+ Remote Hub

Voraussetzungen auf beiden Geräten:
- **Tailscale** installiert und eingeloggt (gleicher Account)
- **S8 Hub** läuft: `s8-hub-start`
- Token aus `~/s8_remote/.env` notieren
- Tailscale-IP des S8+: `tailscale ip -4` → z.B. `100.64.12.34`

Platzhalter in allen URLs ersetzen:
- `S8_IP` → deine Tailscale-IP
- `TOKEN` → dein `S8_HUB_TOKEN`
- `PORT` → Standard `8768`

---

## Shortcut 1: S8 Status

1. Kurzbefehle-App → **+** → Name: `S8 Status`
2. Aktion **URL abrufen**
   - URL: `http://S8_IP:PORT/status?token=TOKEN`
   - Methode: GET
3. Aktion **Ergebnis anzeigen** (oder **Schnellansicht**)
4. Optional: Widget zum Home-Screen

---

## Shortcut 2: S8 Standort

1. Name: `S8 Standort`
2. **URL abrufen**
   - URL: `http://S8_IP:PORT/location?token=TOKEN`
3. **JSON-Wert abrufen** → Pfad z.B. `data.latitude` und `data.longitude` (falls termux-location JSON liefert)
4. **Karte anzeigen** oder Koordinaten in Zwischenablage

Fallback wenn nur Text: **Ergebnis anzeigen**

---

## Shortcut 3: S8 Kamera (Foto)

1. Name: `S8 Kamera`
2. **URL abrufen**
   - URL: `http://S8_IP:PORT/camera?token=TOKEN`
   - Methode: **POST**
   - Header: `Content-Type: application/json`
   - Anfrageinhalt: `{"camera":"0"}`
     - `0` = Rückkamera, `1` = Frontkamera
3. **JSON-Wert abrufen** → `base64`
4. **Base64 dekodieren** → **In Foto speichern** oder **Schnellansicht**

---

## Shortcut 4: Isaac / Agenten Status

1. Name: `S8 Isaac`
2. **URL abrufen**
   - URL: `http://S8_IP:PORT/isaac/status?token=TOKEN`
3. **Ergebnis anzeigen**

Variante alle Agenten:
- URL: `http://S8_IP:PORT/agents?token=TOKEN`

---

## Shortcut 5: S8 Dateien (Downloads)

1. Name: `S8 Dateien`
2. **URL abrufen**
   - URL: `http://S8_IP:PORT/files/list?token=TOKEN&path=~/storage/downloads`
3. **Ergebnis anzeigen** (Liste der Dateinamen)

Einzelne Datei holen:
- URL: `http://S8_IP:PORT/files/download?token=TOKEN&path=/voller/pfad/datei.jpg`
- Base64 dekodieren → speichern

---

## Shortcut 6: Bildschirm (VNC-Info)

Der Hub liefert Verbindungsdaten; die eigentliche Bildschirm-App ist **VNC Viewer**.

1. Name: `S8 Bildschirm Info`
2. **URL abrufen**
   - URL: `http://S8_IP:PORT/screen/info?token=TOKEN`
3. **Ergebnis anzeigen** → VNC-URL z.B. `vnc://100.x.x.x:5900`
4. Manuell in **VNC Viewer** öffnen (Passwort aus droidVNC-NG)

Tipp: VNC Viewer erlaubt gespeicherte Verbindungen — einmal einrichten, danach ein Tap.

---

## Shortcut 7: S8 Menü (alles in einem)

1. Name: `S8 Menü`
2. **Aus Menü wählen** mit:
   - Status
   - Standort
   - Kamera
   - Dateien
   - Isaac
3. **Wenn** Auswahl = Status → URL `.../status?...`
4. **Wenn** Auswahl = Standort → URL `.../location?...`
5. usw.

---

## Sicherheit

- Token **nicht** in Screenshots teilen
- Hub nur über **Tailscale** nutzen, kein Port-Forwarding ins Internet
- Optional Token nur im Header statt Query:
  - Kurzbefehle: Header `X-Hub-Token: TOKEN`

---

## API-Übersicht

| Endpoint | Methode | Funktion |
|----------|---------|----------|
| `/health` | GET | ohne Token |
| `/status` | GET | Hub + Isaac erreichbar? |
| `/location` | GET | GPS |
| `/camera` | POST | Foto |
| `/files/list` | GET | Verzeichnis |
| `/files/download` | GET | Datei als Base64 |
| `/screen/info` | GET | VNC/SSH Infos |
| `/agents` | GET | HTTP/Shell/Unix-Agenten |
| `/agents/isaac/health` | GET | Isaac prüfen |
| `/isaac/status` | GET | Isaac Monitor-State |
| `/isaac/tools` | GET | Live-Tools |