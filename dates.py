from datetime import datetime



release_251 = "251"
dates251 = "2024-10-28 .. 2025-04-02"
START_DATE_251 = datetime(2024, 12, 28)
END_DATE_251 = datetime(2025, 4, 2)
dates_251_available_in = "2025.1.*"
planned_251 = "resharper-stat/planned-2025.1"

release_243 = "243"
dates243_2weeks = "2024-10-13 .. 2024-10-27"
# dates243_1 = "2024-08-15 .. 2024-08-19" No 243.1 bugfix - skipped due to Rider
dates243_2 = "2024-10-13 .. 2024-12-11"
dates243_3 = "2024-12-12 .. 2024-12-24"
dates243 = "2024-08-15 .. 2024-10-12"
START_DATE_243 = datetime(2024, 8, 15)
END_DATE_243 = datetime(2024, 10, 12)
dates_243_available_in = "2024.3.*"
planned_243 = "resharper-stat/planned-2024.3"

release_242 = "242"
dates242_2weeks = "2024-08-15 .. 2024-08-29"
dates242_1 = "2024-08-15 .. 2024-08-19"
dates242_2 = "2024-08-20 .. 2024-08-25"
dates242_3 = "2024-08-26 .. 2024-08-30"
dates242 = "2024-04-10 .. 2024-08-14"
START_DATE_242 = datetime(2024, 4, 10)
END_DATE_242 = datetime(2024, 8, 14)
dates_242_available_in = "2024.2.*"

release_241 = "241"
dates241_2weeks = "2024-04-10 .. 2024-04-24"
dates241 = "2023-12-07 .. 2024-04-09"

release_233 = "233"
dates233_2weeks = "2023-12-07 .. 2023-12-21"
dates233 = "2023-08-02 .. 2023-12-06"

release_232 = "232"
dates232_2weeks = "2023-08-02 .. 2023-08-16"
dates232 = "2023-04-05 .. 2023-08-01"

year_2024 = "2024-01-01 .. 2025-01-01"
year_2025 = "2025-01-01 .. 2026-01-01"

# TODO: update values below
# CURRENT DATES
current_release = release_243
current_release_dates = dates243
current_release_2weeks = dates243_2weeks
current_release_available_in = dates_243_available_in
current_release_START_DATE = START_DATE_243
current_release_END_DATE = END_DATE_243
current_release_planned_tag = planned_243
REGEX_FOR_AVAILABLE_VERSION = r'2024\.3\.[^\s]*'