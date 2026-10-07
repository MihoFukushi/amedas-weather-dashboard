with daily as (

    select * from {{ ref('daily_station_weather') }}

),

aggregated as (

    select
        observation_date,
        pref_code,
        pref_name,
        region,
        count(distinct station_id)      as station_count,
        max(temp_max_c)                 as temp_max_c,
        min(temp_min_c)                 as temp_min_c,
        round(avg(temp_avg_c), 1)       as temp_avg_c,
        round(avg(precipitation_mm), 1) as precipitation_avg_mm,
        max(precipitation_mm)           as precipitation_max_mm,
        max(wind_max_ms)                as wind_max_ms
    from daily
    group by all

),

hottest_station as (

    select
        observation_date,
        pref_code,
        station_name as hottest_station_name
    from daily
    where temp_max_c is not null
    qualify row_number() over (
        partition by observation_date, pref_code
        order by temp_max_c desc, station_id
    ) = 1

)

select
    a.*,
    h.hottest_station_name
from aggregated as a
left join hottest_station as h
    on a.observation_date = h.observation_date
    and a.pref_code = h.pref_code
