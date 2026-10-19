# CowSafe Tag

A smart neck tag for cows that keeps them inside a **virtual boundary**, away from **garbage and plastic**, and lets the farmer watch their **health** from a phone.

Programmed fully in **Python**.

## The problem

Cows wander onto busy roads, eat plastic from garbage dumps, and damage crops. Farmers cannot watch them all day, and fences are costly. There is no simple, low-cost way to keep cows safe and to know when their health is going wrong.

## What it does

- **Virtual boundary:** the farmer draws a safe area on the phone map. No fence is needed.
- **Step-by-step warning:** a light vibration near the edge, then a very mild pulse if the cow still crosses. The strength is adjustable, with a daily limit and an automatic switch-off.
- **Cow trains itself:** over time the cow learns to avoid danger areas without help from the farmer.
- **Plastic Guard:** garbage spots are red zones. The farmer gets an alert if the cow sniffs and chews near one.
- **Health monitoring:** eating, chewing, water, temperature and activity, with early sickness alerts.

## Technology stack

Python, MicroPython on ESP32, GPS (NEO-6M), motion sensor (MPU6050), temperature sensor (DS18B20), GSM (SIM800L) or LoRa (SX1278), Shapely, Pandas, NumPy, scikit-learn, Flask, Firebase.

> Edit this list so it matches exactly what you used.

## Project structure

```
main.py                  main program
cowsafe/
  boundary.py            virtual boundary and red zones
  warnings.py            vibration, mild pulse, daily limit
  plastic_guard.py       plastic guard alerts
  health.py              health monitoring
  alerts.py              alerts and reports to the phone
  sensors.py             GPS, motion and temperature sensors (or simulation)
  app.py                 backend and dashboard
tests/                   tests
docs/                    abstract, diagrams, photos
data/                    sample data
```

## How to run

```sh
python -m venv .venv
source .venv/bin/activate        # on Windows: .venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Run the tests with `python -m pytest`.

## Safety note

Pulse strength, the daily limit and all health thresholds must be set with a veterinarian before any use on a real animal.

## Status

Prototype. Add what is built and tested here.

## Team

Add your team name and members here.

## License

MIT. See [LICENSE](LICENSE).
