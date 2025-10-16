#  Modbus Configuration for the Single-Phase Meter

This document details the specific Modbus configuration used to communicate with the single-phase smart meter in this project. It covers the physical connection, communication parameters, and the final register map that was discovered through experimentation.

---

## 1. Physical Connection 

The meter communicates via the RS485 protocol. A USB-to-RS485 converter using a **CH340 chipset** was used to connect the meter to the host computer (Ubuntu Linux).

-   **Wiring:** The connection is a simple two-wire, half-duplex setup:
    -   Converter **A+** terminal is connected to the meter's **A+** terminal.
    -   Converter **B-** terminal is connected to the meter's **B-** terminal.

---

## 2. Communication Parameters

These are the low-level settings required to establish a stable serial connection.

-   **Port:** Auto-detected by the script (typically `/dev/ttyUSB0` on Linux).
-   **Baud Rate:** `9600`
-   **Parity:** None
-   **Stop Bits:** 1
-   **Data Bits:** 8
-   **Slave ID:** `1`

---

## 3. Register Map 

This is the final, verified map of Modbus holding registers used to read data. All values are 32-bit floating-point numbers, each occupying two consecutive registers.

| Metric              | Register Address (Hex) | Register Address (Dec) | Data Type | Word Order | Scale Factor | Notes                                                 |
| ------------------- | ---------------------- | ---------------------- | --------- | ---------- | ------------ | ----------------------------------------------------- |
| Voltage             | `0x0006`               | 6                      | `float32` | `ABCD`     | `1.0`        | Direct reading in Volts.                          |
| Current             | `0x0008`               | 8                      | `float32` | `ABCD`     | `1.0`        | Direct reading in Amperes.                        |
| Active Power        | `0x000A`               | 10                     | `float32` | `ABCD`     | `-1000.0`    | Meter returns negative kW; scaled to positive Watts.  |
| Power Factor        | `0x0022`               | 34                     | `float32` | `ABCD`     | `1.0`        | A value between 0.0 and 1.0.                      |
| Frequency           | `0x0036`               | 54                     | `float32` | `ABCD`     | `1.0`        | Direct reading in Hertz.                          |
| Cumulative Energy   | `0x0038`               | 56                     | `float32` | `ABCD`     | `1.0`        | Meter directly provides cumulative kWh.               |

---

## 4. The Discovery Process 

The final register map, particularly the `word_order` and `scale` factors, was determined through experimentation using the `dump.py` script and by observing the data on the live dashboard.

-   **Initial Scans:** The `dump.py` script was used to scan a range of registers. This helped identify which addresses were returning valid-looking floating-point numbers.

-   **`word_order` Calibration:** Initially, some values like Frequency were returning incorrect, large numbers. The `dump.py` script helped test different byte orderings. It was discovered that the default `ABCD` (Big Endian) was correct for all registers on this meter, contrary to some meters that require a `BADC` swap.

-   **`scale` Factor Calibration:**
    -   **Active Power:** The meter returned a small, negative value (e.g., -0.450). This indicated it was sending data in negative kilowatts. A scaling factor of `-1000.0` was applied to convert it to positive Watts.
    -   **Cumulative Energy:** Early tests with a `0.001` scale factor (assuming the meter sent Watt-hours) resulted in extremely low daily consumption values. Through a controlled load test, it was confirmed that the meter sends the cumulative value **directly in kWh**, so the correct scaling factor is `1.0`.
