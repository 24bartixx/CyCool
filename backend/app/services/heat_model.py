"""UTCI per place from real inputs: summer weather, local sun exposure and ground surface temperature.

UTCI needs air temperature, humidity, wind and the mean radiant temperature (MRT, the heat a person
receives as radiation). Weather is real (ERA5 reanalysis via Open-Meteo, table weather_hour). MRT is built
per place with the ERA5-HEAT formula (Di Napoli et al. 2020, as implemented in ECMWF thermofeel):

    MRT^4 * sigma = 0.5 L_down + 0.5 L_up + (0.7 / 0.97) * (0.5 D + 0.5 albedo G + f_p * sun_share * DNI)

  - the direct sun term is scaled by the place's share of direct sun (from the real solar index)
  - L_up is the longwave from the ground, from its real Landsat surface temperature brought to the design
    hour: design air temperature + (Landsat LST - air temperature at the ~10:30 overpass)
  - L_down (sky longwave) uses Brutsaert's clear-sky emissivity, as the weather source has no longwave
  - diffuse light and sky view are not reduced in shade (not modelled)

UTCI itself is the official polynomial (Broede et al. 2012), also from thermofeel (Apache 2.0).
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import datetime
from statistics import mean, median
from typing import Any

import numpy as np
import thermofeel

SIGMA = 5.67e-8  # Stefan-Boltzmann, W m-2 K-4
K = 273.15


@dataclass(frozen=True)
class DesignWeather:
    """The summer afternoon the model is evaluated for: the mean of the hot days at the design hour."""

    hour: int
    days: int  # hot days averaged
    days_total: int
    temp_c: float
    rh_pct: float
    wind_ms: float
    ghi_wm2: float  # global horizontal
    dhi_wm2: float  # diffuse horizontal
    direct_h_wm2: float  # direct on a horizontal plane
    dni_wm2: float  # direct normal
    overpass_temp_c: float  # typical air temperature at the Landsat overpass (~10:30)

    @property
    def cos_zenith(self) -> float:
        return self.direct_h_wm2 / self.dni_wm2 if self.dni_wm2 > 1 else 0.0

    @property
    def vapour_hpa(self) -> float:
        return float(thermofeel.calculate_saturation_vapour_pressure(np.array(self.temp_c + K))) * self.rh_pct / 100

    def as_dict(self) -> dict[str, Any]:
        return {k: round(v, 2) if isinstance(v, float) else v for k, v in asdict(self).items()}


def design_weather(rows: list[dict[str, Any]], hour: int, hot_pct: float, overpass_hours: list[int]) -> DesignWeather:
    """Hot-day composite: the days whose air temperature at `hour` is at or above the `hot_pct` percentile
    of all days, each variable averaged over those days at that hour (so the values come from the same real
    afternoons and stay physically consistent). The overpass temperature is the median over all days of the
    mean of `overpass_hours`, like the Landsat median composite it is compared with."""

    def at(r: dict[str, Any]) -> datetime:
        return r["time"] if isinstance(r["time"], datetime) else datetime.fromisoformat(str(r["time"]))

    at_hour = [r for r in rows if at(r).hour == hour]
    if not at_hour:
        raise RuntimeError(f"weather_hour has no rows at {hour}:00. Run: python scripts/export_to_db.py")
    temps = sorted(float(r["temp_c"]) for r in at_hour)
    cut = float(np.percentile(temps, hot_pct))
    hot = [r for r in at_hour if float(r["temp_c"]) >= cut]

    by_day: dict[str, list[float]] = {}
    for r in rows:
        if at(r).hour in overpass_hours:
            by_day.setdefault(at(r).date().isoformat(), []).append(float(r["temp_c"]))

    def avg(key: str) -> float:
        return mean(float(r[key]) for r in hot)

    return DesignWeather(
        hour=hour,
        days=len(hot),
        days_total=len(at_hour),
        temp_c=avg("temp_c"),
        rh_pct=avg("rh_pct"),
        wind_ms=avg("wind_ms"),
        ghi_wm2=avg("ghi_wm2"),
        dhi_wm2=avg("dhi_wm2"),
        direct_h_wm2=avg("direct_h_wm2"),
        dni_wm2=avg("dni_wm2"),
        overpass_temp_c=median(mean(v) for v in by_day.values()),
    )


def ground_temp_c(w: DesignWeather, lst_c: float) -> float:
    """Ground surface temperature at the design hour: the Landsat excess over the air at the overpass,
    added to the design-hour air temperature (conservative: the midday excess is usually larger)."""
    return w.temp_c + (lst_c - w.overpass_temp_c)


def mean_radiant_temp_c(w: DesignWeather, sun_share: float, ground_c: float, albedo: float, ground_emissivity: float) -> float:
    ta_k = w.temp_c + K
    eps_sky = 1.24 * (w.vapour_hpa / ta_k) ** (1 / 7)  # Brutsaert (1975), clear sky
    l_down = eps_sky * SIGMA * ta_k**4
    l_up = ground_emissivity * SIGMA * (ground_c + K) ** 4 + (1 - ground_emissivity) * l_down
    mrt_k = thermofeel.calculate_mean_radiant_temperature(
        ssrd=np.array(w.ghi_wm2),
        ssr=np.array(w.ghi_wm2 * (1 - albedo)),
        dsrp=np.array(w.dni_wm2 * max(0.0, min(1.0, sun_share))),
        strd=np.array(l_down),
        fdir=np.array(w.direct_h_wm2),
        strr=np.array(l_down - l_up),
        cossza=np.array(w.cos_zenith),
    )
    return float(mrt_k) - K


def utci_c(w: DesignWeather, mrt_c: float) -> float:
    value = thermofeel.calculate_utci(
        t2_k=np.array(w.temp_c + K), va=np.array(w.wind_ms), mrt=np.array(mrt_c + K), ehPa=np.array(w.vapour_hpa)
    )
    result = float(value) - K
    if not math.isfinite(result):
        raise ValueError(f"UTCI is not finite for MRT {mrt_c:.1f} °C")
    return result


def place_heat(w: DesignWeather, sun_share: float, lst_c: float, albedo: float, ground_emissivity: float) -> dict[str, float]:
    """UTCI and its inputs at one place."""
    ground = ground_temp_c(w, lst_c)
    mrt = mean_radiant_temp_c(w, sun_share, ground, albedo, ground_emissivity)
    return {
        "utci_c": round(utci_c(w, mrt), 3),
        "mrt_c": round(mrt, 2),
        "ground_temp_c": round(ground, 2),
        "sun_share": round(sun_share, 3),
    }
