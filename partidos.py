#!/usr/bin/env python3
"""Genera un calendario .ics combinado con los partidos de mis equipos.

Fuente: API pública de ESPN (site.api.espn.com), sin clave.
Configuración: equipos.json (equipos, ID de ESPN y competiciones que juega cada uno).
Uso: python3 partidos.py [--salida partidos.ics] [--config equipos.json]
Solo usa la biblioteca estándar de Python.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

try:
    from zoneinfo import ZoneInfo

    TZ_LOCAL = ZoneInfo("America/Guatemala")
except Exception:  # pragma: no cover - entorno sin tzdata
    TZ_LOCAL = timezone(timedelta(hours=-6))

BASE = "https://site.api.espn.com/apis/site/v2/sports"
UA = "Mozilla/5.0 (mis-partidos calendar generator)"

DURACION = {  # duración aproximada del evento en el calendario
    "soccer": timedelta(hours=2),
    "basketball": timedelta(hours=2, minutes=30),
    "baseball": timedelta(hours=3),
    "football": timedelta(hours=3, minutes=30),
}

NOMBRE_LIGA = {
    "esp.1": "LaLiga",
    "esp.copa_del_rey": "Copa del Rey",
    "esp.super_cup": "Supercopa de España",
    "uefa.champions": "Champions League",
    "uefa.europa": "Europa League",
    "uefa.europa.conf": "Conference League",
    "uefa.super_cup": "Supercopa de Europa",
    "fifa.cwc": "Mundial de Clubes",
    "club.friendly": "Amistoso",
    "nba": "NBA",
    "mlb": "MLB",
    "nfl": "NFL",
    "fifa.friendly": "Amistoso internacional",
    "concacaf.nations.league": "Liga de Naciones Concacaf",
    "fifa.worldq.concacaf": "Eliminatoria mundialista Concacaf",
    "concacaf.gold": "Copa Oro",
    "fifa.world": "Copa del Mundo",
    "gua.1": "Liga Nacional de Guatemala",
    "concacaf.central_american_cup": "Copa Centroamericana",
    "concacaf.champions": "Copa de Campeones Concacaf",
}

# Ligas de EE. UU.: la temporada se identifica por año y tipo (2 = regular, 3 = playoffs)
LIGAS_EEUU = {"nba", "mlb", "nfl"}


# ---------------------------------------------------------------- red

def get_json(url: str, intentos: int = 3) -> dict | None:
    for i in range(intentos):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (400, 404):
                return None  # liga/temporada sin datos: normal
            err = e
        except Exception as e:  # red, timeout, JSON inválido
            err = e
        time.sleep(2 * (i + 1))
    print(f"  ! sin respuesta: {url} ({err})", file=sys.stderr)
    return None


def urls_equipo(eq: dict, hoy: date, dias_atras: int) -> list[tuple[str, str]]:
    """Devuelve (liga, url) a consultar para un equipo."""
    dep, tid = eq["deporte"], eq["espn_id"]
    urls = []
    for lg in eq["ligas"]:
        sched = f"{BASE}/{dep}/{lg}/teams/{tid}/schedule"
        if lg in LIGAS_EEUU:
            for season in ("", f"&season={hoy.year}", f"&season={hoy.year + 1}"):
                for st in (2, 3):
                    urls.append((lg, f"{sched}?seasontype={st}{season}"))
        else:
            urls.append((lg, sched))
            urls.append((lg, f"{sched}?fixture=true"))
            ini = (hoy - timedelta(days=dias_atras)).strftime("%Y%m%d")
            fin = (hoy + timedelta(days=300)).strftime("%Y%m%d")
            urls.append((lg, f"{BASE}/{dep}/{lg}/scoreboard?dates={ini}-{fin}&limit=1000"))
    return urls


# ---------------------------------------------------------------- parseo

def _score(c: dict) -> str | None:
    s = c.get("score")
    if isinstance(s, dict):
        s = s.get("displayValue") or (s.get("value") if s.get("value") is not None else None)
    if s is None or s == "":
        return None
    try:
        f = float(s)
        return str(int(f)) if f.is_integer() else str(s)
    except (TypeError, ValueError):
        return str(s)


def _tv(comp: dict) -> list[str]:
    nombres: list[str] = []
    for b in comp.get("broadcasts") or []:
        if isinstance(b.get("names"), list):
            nombres += [n for n in b["names"] if n]
        media = b.get("media") or {}
        if media.get("shortName"):
            nombres.append(media["shortName"])
    for g in comp.get("geoBroadcasts") or []:
        n = (g.get("media") or {}).get("shortName")
        if n:
            nombres.append(n)
    vistos, out = set(), []
    for n in nombres:
        if n not in vistos:
            vistos.add(n)
            out.append(n)
    return out


def _parse_fecha(s: str) -> datetime | None:
    s = s.strip().replace("Z", "+00:00")
    for fmt in (None, "%Y-%m-%dT%H:%M%z"):
        try:
            d = datetime.fromisoformat(s) if fmt is None else datetime.strptime(s, fmt)
            return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def parse_evento(ev: dict, liga: str, deporte: str) -> dict | None:
    comps = ev.get("competitions") or []
    if not comps:
        return None
    comp = comps[0]
    inicio = _parse_fecha(ev.get("date") or comp.get("date") or "")
    if inicio is None:
        return None

    local = visita = None
    for c in comp.get("competitors") or []:
        t = c.get("team") or {}
        info = {
            "id": str(t.get("id") or c.get("id") or ""),
            "nombre": t.get("displayName") or t.get("shortDisplayName") or t.get("name") or "?",
            "score": _score(c),
        }
        if c.get("homeAway") == "home":
            local = info
        else:
            visita = info
    if not local or not visita:
        return None

    status = comp.get("status") or ev.get("status") or {}
    st = status.get("type") or {}
    tipo_temp = (ev.get("seasonType") or {}).get("type")
    notas = [n.get("headline") for n in comp.get("notes") or [] if n.get("headline")]
    venue = comp.get("venue") or {}
    ciudad = ", ".join(x for x in ((venue.get("address") or {}).get("city"), (venue.get("address") or {}).get("country")) if x)
    link = None
    for l in ev.get("links") or []:
        rels = l.get("rel") or []
        if "summary" in rels or "gamecast" in rels or "boxscore" in rels:
            link = l.get("href")
            break
    if not link and ev.get("links"):
        link = ev["links"][0].get("href")

    hora_valida = ev.get("timeValid", comp.get("timeValid", True))
    if st.get("name") in ("STATUS_TBD",):
        hora_valida = False

    return {
        "id": str(ev.get("id")),
        "liga": liga,
        "deporte": deporte,
        "inicio": inicio,
        "hora_valida": bool(hora_valida),
        "local": local,
        "visita": visita,
        "estado": st.get("state") or "pre",          # pre | in | post
        "completo": bool(st.get("completed")),
        "estado_nombre": st.get("name") or "",
        "detalle": st.get("shortDetail") or st.get("detail") or "",
        "playoffs": tipo_temp == 3,
        "notas": notas,
        "estadio": venue.get("fullName"),
        "ciudad": ciudad,
        "tv": _tv(comp),
        "link": link,
    }


# ---------------------------------------------------------------- ICS

def esc(t: str) -> str:
    return t.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def fold(line: str) -> str:
    """Pliega líneas a 75 octetos (RFC 5545) sin cortar caracteres UTF-8."""
    out, cur, n = [], "", 0
    for ch in line:
        b = len(ch.encode("utf-8"))
        if n + b > 75:
            out.append(cur)
            cur, n = " " + ch, 1 + b
        else:
            cur += ch
            n += b
    out.append(cur)
    return "\r\n".join(out)


def ts(d: datetime) -> str:
    return d.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def titulo(p: dict, emoji: str) -> str:
    L, V = p["local"], p["visita"]
    eeuu = p["liga"] in LIGAS_EEUU
    if p["estado"] in ("post", "in") and L["score"] is not None and V["score"] is not None:
        if eeuu:
            core = f"{V['nombre']} {V['score']} @ {L['nombre']} {L['score']}"
        else:
            core = f"{L['nombre']} {L['score']}-{V['score']} {V['nombre']}"
        if p["estado"] == "in":
            core += " (en vivo)"
    else:
        core = f"{V['nombre']} @ {L['nombre']}" if eeuu else f"{L['nombre']} vs {V['nombre']}"
    n = p["estado_nombre"]
    if n == "STATUS_POSTPONED":
        core = "APLAZADO · " + core
    elif n in ("STATUS_CANCELED", "STATUS_CANCELLED"):
        core = "CANCELADO · " + core
    elif n == "STATUS_SUSPENDED":
        core = "SUSPENDIDO · " + core
    return f"{emoji} {core}"


def descripcion(p: dict) -> str:
    comp = NOMBRE_LIGA.get(p["liga"], p["liga"])
    if p["playoffs"]:
        comp += " · Playoffs"
    lineas = [comp + (" · " + " · ".join(p["notas"]) if p["notas"] else "")]
    if p["estado"] == "post" and p["detalle"]:
        lineas.append(f"Resultado: {p['detalle']}")
    if not p["hora_valida"]:
        lineas.append("Hora por confirmar")
    if p["estadio"]:
        lineas.append("Estadio: " + p["estadio"] + (f" ({p['ciudad']})" if p["ciudad"] else ""))
    if p["tv"]:
        lineas.append("TV (EE. UU.): " + ", ".join(p["tv"]))
    if p["link"]:
        lineas.append(p["link"])
    return "\n".join(lineas)


def vevent(p: dict, emoji: str, ahora: datetime) -> list[str]:
    lines = ["BEGIN:VEVENT", f"UID:espn-{p['id']}@mis-partidos", f"DTSTAMP:{ts(ahora)}"]
    if p["hora_valida"]:
        fin = p["inicio"] + DURACION.get(p["deporte"], timedelta(hours=2))
        lines += [f"DTSTART:{ts(p['inicio'])}", f"DTEND:{ts(fin)}"]
    else:
        dia = p["inicio"].astimezone(TZ_LOCAL).date()
        lines += [f"DTSTART;VALUE=DATE:{dia:%Y%m%d}", f"DTEND;VALUE=DATE:{dia + timedelta(days=1):%Y%m%d}"]
    lines.append(f"SUMMARY:{esc(titulo(p, emoji))}")
    lines.append(f"DESCRIPTION:{esc(descripcion(p))}")
    loc = ", ".join(x for x in (p["estadio"], p["ciudad"]) if x)
    if loc:
        lines.append(f"LOCATION:{esc(loc)}")
    if p["link"]:
        lines.append(f"URL:{p['link']}")
    lines.append(f"CATEGORIES:{esc(NOMBRE_LIGA.get(p['liga'], p['liga']))}")
    if p["estado_nombre"] in ("STATUS_CANCELED", "STATUS_CANCELLED"):
        lines.append("STATUS:CANCELLED")
    else:
        lines.append("STATUS:CONFIRMED" if p["hora_valida"] else "STATUS:TENTATIVE")
    lines += ["TRANSP:TRANSPARENT", "END:VEVENT"]
    return lines


def construir_ics(partidos: list[tuple[dict, str]], nombre_cal: str, ahora: datetime) -> str:
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//mis-partidos//ESPN//ES",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{esc(nombre_cal)}",
        "X-WR-CALDESC:Partidos de mis equipos (fuente: ESPN). Se actualiza automáticamente.",
        "X-WR-TIMEZONE:America/Guatemala",
        "REFRESH-INTERVAL;VALUE=DURATION:PT6H",
        "X-PUBLISHED-TTL:PT6H",
    ]
    for p, emoji in sorted(partidos, key=lambda x: x[0]["inicio"]):
        lines += vevent(p, emoji, ahora)
    lines.append("END:VCALENDAR")
    return "\r\n".join(fold(l) for l in lines) + "\r\n"


# ---------------------------------------------------------------- main

def recolectar(cfg: dict, fetch=get_json, hoy: date | None = None) -> tuple[list[tuple[dict, str]], dict]:
    hoy = hoy or datetime.now(TZ_LOCAL).date()
    dias_atras = int(cfg.get("dias_atras", 45))
    limite = datetime.combine(hoy - timedelta(days=dias_atras), datetime.min.time(), tzinfo=timezone.utc)
    por_id: dict[str, tuple[dict, str]] = {}
    conteo: dict[str, int] = {}
    for eq in cfg["equipos"]:
        tid = str(eq["espn_id"])
        ids_eq = set()
        print(f"- {eq['nombre']}", file=sys.stderr)
        for liga, url in urls_equipo(eq, hoy, dias_atras):
            data = fetch(url)
            if not data:
                continue
            for ev in data.get("events") or []:
                p = parse_evento(ev, liga, eq["deporte"])
                if not p or p["inicio"] < limite:
                    continue
                # el scoreboard trae toda la liga: quedarse solo con partidos del equipo
                if tid not in (p["local"]["id"], p["visita"]["id"]):
                    continue
                key = p["id"]
                previo = por_id.get(key)
                # si llega el mismo partido de dos fuentes, quedarse con el más informativo
                if previo is None or _rango(p) > _rango(previo[0]):
                    por_id[key] = (p, eq.get("emoji", ""))
                ids_eq.add(key)
        conteo[eq["nombre"]] = len(ids_eq)
        print(f"  {len(ids_eq)} partidos", file=sys.stderr)
    return list(por_id.values()), conteo


def _rango(p: dict) -> tuple:
    return (p["estado"] == "post", p["estado"] == "in", p["hora_valida"], len(p["tv"]), bool(p["estadio"]))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(Path(__file__).with_name("equipos.json")))
    ap.add_argument("--salida", default=str(Path(__file__).with_name("partidos.ics")))
    a = ap.parse_args()

    cfg = json.loads(Path(a.config).read_text(encoding="utf-8"))
    partidos, conteo = recolectar(cfg)
    if not partidos:
        print("ERROR: ESPN no devolvió ningún partido; no se sobrescribe el calendario.", file=sys.stderr)
        return 1
    vacios = [n for n, c in conteo.items() if c == 0]
    if vacios:
        print("Aviso: sin partidos para " + ", ".join(vacios), file=sys.stderr)

    # DTSTAMP truncado al día: el archivo solo cambia cuando cambian los partidos (o una vez al día)
    ahora = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    ics = construir_ics(partidos, cfg.get("calendario", "Mis Equipos"), ahora)
    Path(a.salida).write_text(ics, encoding="utf-8", newline="")
    estado = {"actualizado": ahora.date().isoformat(), "total": len(partidos), "por_equipo": conteo}
    Path(a.salida).with_name("estado.json").write_text(
        json.dumps(estado, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"OK: {len(partidos)} partidos -> {a.salida}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
