{{
    config(
        materialized='incremental',
        unique_key=['station_id', 'observed_at'],
        incremental_strategy='delete+insert'
    )
}}

{#-
  時別の観測ファクト。incremental にして、2回目以降は直近1日分だけ再計算する
  (delete+insert で重複を防ぐ)。--full-refresh で全件作り直せる。
-#}

with observations as (

    select * from {{ ref('stg_amedas__observations') }}

    {% if is_incremental() %}
    where observed_at > (
        select coalesce(max(observed_at), cast('1900-01-01' as timestamp)) - interval 1 day
        from {{ this }}
    )
    {% endif %}

),

stations as (

    select * from {{ ref('stg_amedas__stations') }}

),

prefs as (

    select * from {{ ref('jma_pref_codes') }}

)

select
    o.station_id,
    o.observed_at,
    o.observation_date,
    o.observation_hour,
    s.station_name,
    s.station_name_en,
    s.pref_code,
    p.pref_name,
    p.region,
    s.latitude,
    s.longitude,
    s.altitude_m,
    o.temperature_c,
    o.humidity_pct,
    o.precipitation_1h_mm,
    o.precipitation_24h_mm,
    o.wind_speed_ms,
    o.wind_direction_code,
    o.pressure_hpa,
    o.sunshine_1h_h,
    o.snow_depth_cm
from observations as o
left join stations as s on o.station_id = s.station_id
left join prefs as p on s.pref_code = p.pref_code
