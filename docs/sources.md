# Data And Evidence Sources

All runtime APIs are free and keyless for this assignment.

| Source | Use in product | Access |
|---|---|---|
| [Open-Meteo Weather Forecast API](https://open-meteo.com/en/docs) | Hourly temperature, apparent temperature, precipitation, humidity, and wind forecasts | Keyless |
| [Open-Meteo Air Quality API](https://open-meteo.com/en/docs/air-quality-api) | Hourly PM2.5 and PM10 forecasts | Keyless |
| [NASA POWER Daily API](https://power.larc.nasa.gov/docs/services/api/temporal/daily/) | Five complete years of daily historical weather for local percentile baselines | Keyless |

## Scenario Evidence References

The governed signal catalog stores a source reference with every rule. Important supporting references
include:

- [Central Pollution Control Board National AQI](https://airquality.cpcb.gov.in/AQI_India/) for Indian air
  quality context.
- [WHO Global Air Quality Guidelines](https://www.who.int/publications/i/item/9789240034228) for particulate
  pollution context.

Rule thresholds and chronic-condition mappings remain prototype operational logic. The references support
the scenario direction but do not constitute clinical approval of the implemented thresholds.
