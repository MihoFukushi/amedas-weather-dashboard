with source as (

    select * from {{ source('amedas', 'stations') }}

),

renamed as (

    select
        cast(station_id as varchar)   as station_id,
        cast(pref_code as varchar)    as pref_code,
        station_type,
        name_kanji                    as station_name,
        name_kana                     as station_name_kana,
        name_en                       as station_name_en,
        cast(latitude as double)      as latitude,
        cast(longitude as double)     as longitude,
        cast(altitude_m as integer)   as altitude_m,
        cast(extracted_at as timestamp) as extracted_at
    from source

)

select * from renamed
