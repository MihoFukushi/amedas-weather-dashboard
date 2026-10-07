with hourly as (

    select * from {{ ref('fct_observations_hourly') }}

)

select
    observation_date,
    station_id,
    station_name,
    pref_code,
    pref_name,
    region,
    latitude,
    longitude,
    count(*)                                   as observation_count,
    count(*) = 24                              as is_complete_day,
    max(temperature_c)                         as temp_max_c,
    min(temperature_c)                         as temp_min_c,
    round(avg(temperature_c), 1)               as temp_avg_c,
    sum(precipitation_1h_mm)                   as precipitation_mm,
    max(wind_speed_ms)                         as wind_max_ms,
    sum(sunshine_1h_h)                         as sunshine_h,
    max(snow_depth_cm)                         as snow_depth_max_cm,
    round(avg(humidity_pct), 0)                as humidity_avg_pct
from hourly
group by all
