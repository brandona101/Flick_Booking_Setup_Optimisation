/****** Object:  View [dbo].[agb_ABS_Export]    Script Date: 24/04/2026 9:07:34 AM ******/
/****** Object:  View [dbo].[agb_ABS_Export]    Script Date: 14/04/2026 3:13:11 PM ******/
/****** Object:  View [dbo].[agb_ABS_Export]    Script Date: 6/04/2026 3:20:47 PM ******/
CREATE OR ALTER       VIEW [dbo].[agb_ABS_Export] AS

WITH 
-- Aggregate product data to get one row per booking setup
-- Calculates total product count, value and quantity per ABS
ProductAggregates AS (
    SELECT
        msdyn_agreementbookingsetup,
        COUNT(*) AS product_count,
        SUM(ISNULL(msdyn_quantity, 0) * ISNULL(msdyn_unitamount, 0)) AS setup_value,
        SUM(ISNULL(msdyn_quantity, 0)) AS setup_quantity
    FROM
        [dbo].[msdyn_agreementbookingproduct]
    WHERE
        IsDelete IS NULL
    GROUP BY
        msdyn_agreementbookingsetup
),

-- Deduplicate booking setups — keeps latest record per setup ID
UniqueSetups AS (
    SELECT
        *,
        ROW_NUMBER() OVER(PARTITION BY msdyn_agreementbookingsetupid ORDER BY createdon DESC) as rn
    FROM dbo.[msdyn_agreementbookingsetup]
),

-- Decode vel_division option set values to human-readable labels
gopt_division AS (
    SELECT [Option], LocalizedLabel 
    FROM dbo.GlobalOptionsetMetadata 
    WHERE EntityName = 'msdyn_agreement' 
    AND OptionSetName = 'vel_division'
),

-- Decode vel_invoicingfrequency option set values to human-readable labels
gopt_inv_freq AS (
    SELECT [Option], LocalizedLabel 
    FROM dbo.GlobalOptionsetMetadata 
    WHERE EntityName = 'msdyn_agreement' 
    AND OptionSetName = 'vel_invoicingfrequency'
),

-- Deduplicate branch territory table per territory+division combination
-- Used to look up the correct service branch based on FL territory and agreement division
UniqueBranchTerritory AS (
    SELECT
        *,
        ROW_NUMBER() OVER (PARTITION BY vel_territory, vel_division ORDER BY vel_branch) AS rn
    FROM [dbo].[vel_branchterritory]
    WHERE statecode = 0
),

BranchTimezone AS (
    SELECT msdyn_organizationalunitid, utc_offset_minutes
    FROM pbi_branch_details
)

SELECT
    -- -------------------------------------------------------------------------
    -- IDENTIFIERS
    -- -------------------------------------------------------------------------
    s.[Id] AS booking_setup_id,                                         -- Agreement Booking Setup GUID
    s.[vel_functionallocation] AS FL_id,                                -- Functional Location GUID
    COALESCE(s.vel_branch, '') AS branch_id,                            -- Branch GUID

    -- -------------------------------------------------------------------------
    -- MODIFICATION TRACKING
    -- -------------------------------------------------------------------------
    CAST(DATEADD(hh, 10, s.modifiedon) AS DATE) AS last_modifiedon,    -- Last modified date in AEST (+10)
    COALESCE(s.modifiedbyname, '') AS modifiedbyname,                   -- User who last modified

    -- -------------------------------------------------------------------------
    -- AGREEMENT & SETUP NAMES
    -- -------------------------------------------------------------------------
    s.[msdyn_agreementname],            -- Agreement name
    s.[msdyn_name] AS setup_name,                         -- Booking setup name
    CASE
        WHEN s.[msdyn_autogeneratebooking] = 0 THEN 'No'
        ELSE 'Yes'
    END AS auto_generate_booking,                                        -- Whether bookings auto-generate
    a.msdyn_billingaccountname AS billing_account,        -- Billing account name from agreement

    -- -------------------------------------------------------------------------
    -- FUNCTIONAL LOCATION DETAILS
    -- -------------------------------------------------------------------------
    s.[vel_functionallocationname] AS FL_name,            -- FL display name
    fl.vel_locationnumber AS fl_number,                   -- FL location number
    COALESCE(fl.msdyn_city, '') AS city,                                -- FL city
    fl.msdyn_address1 AS [address],
    fl.msdyn_longitude AS longitude,                                     -- FL longitude
    fl.msdyn_latitude AS latitude,                                       -- FL latitude

    -- -------------------------------------------------------------------------
    -- TERRITORY & BRANCH
    -- -------------------------------------------------------------------------
    COALESCE(s.[vel_territoryname], '') AS territory,                   -- Territory name from setup
    COALESCE(div.LocalizedLabel, '') AS division,                       -- Division label (e.g. Hygiene, Commercial Pest)
    COALESCE(s.[vel_branchname], '') AS setup_branch,                   -- Branch on the setup itself
    COALESCE(bt.vel_branchname, '') AS service_branch,                  -- Branch derived from FL territory + division lookup

    -- -------------------------------------------------------------------------
    -- BOOKING FLEXIBILITY & PREFERENCES
    -- -------------------------------------------------------------------------
    s.[msdyn_prebookingflexibility] AS pre_bookingflex,                 -- Days before booking date flexibility
    s.[msdyn_postbookingflexibility] AS post_bookingflex,               -- Days after booking date flexibility
    COALESCE(s.[msdyn_preferredresourcename], '') AS preferred_resource, -- Preferred technician
    CAST(DATEADD(MINUTE, COALESCE(tz.utc_offset_minutes, 0), s.[msdyn_preferredstarttime]) AS time) AS preferred_start_time,               -- Preferred start time (UTC datetime)
    CAST(DATEADD(MINUTE, COALESCE(tz.utc_offset_minutes, 0), s.[msdyn_timewindowstart]) AS time) AS timewindow_start,                      -- Time window start
    CAST(DATEADD(MINUTE, COALESCE(tz.utc_offset_minutes, 0), s.[msdyn_timewindowend]) AS time) AS timewindow_end,                          -- Time window end

    -- -------------------------------------------------------------------------
    -- PRODUCTS & VALUE
    -- -------------------------------------------------------------------------
    COALESCE(s.[vel_productnames], '') AS products,                     -- Comma-separated product names
    freq.services_per_year,                                              -- Calculated services per year based on recurrence
    COALESCE(inv_freq.LocalizedLabel, '') AS invoice_frequency,         -- Invoicing frequency label
    s.[msdyn_estimatedduration] AS service_duration,                    -- Estimated duration in minutes
    ROUND(pa.setup_value, 2) AS setup_value,                            -- Total product value per visit (qty * unit price)
    pa.setup_quantity,                                                   -- Total product quantity per visit
    ROUND(pa.setup_value * freq.services_per_year, 2) AS annual_value,  -- Annualised value (setup_value * services_per_year)

    -- -------------------------------------------------------------------------
    -- WORK ORDER & GENERATION SETTINGS
    -- -------------------------------------------------------------------------
    COALESCE(s.[msdyn_workordersummary], '') AS WO_summary,             -- Work order summary / instructions
    s.msdyn_generatewodaysinadvance AS generate_wos_days_in_advance,    -- Days in advance WOs are generated

    -- -------------------------------------------------------------------------
    -- RECURRENCE STRING & DERIVED FREQUENCY
    -- -------------------------------------------------------------------------
    s.[msdyn_recurrencesettings] AS recurrence_string,                  -- Raw XML recurrence string from Dynamics
    -- Human-readable recurrence label e.g. '4 Weekly', '3 Monthly', 'Yearly'
    recc_freq.recurrence_frequency,
    num_recc.num_recurrences,

    -- Frequency type classification — more granular than recurrence_frequency
    -- Values: Weekly, Weekly - Multi Day, Monthly - Fixed Date, Monthly - Week Pattern, Yearly, Daily
    ftype.frequency_type,

    -- -------------------------------------------------------------------------
    -- DAY OF WEEK
    -- dow_number: numeric DOW value(s) from XML (0=Sun..6=Sat)
    --   For single-day: single integer as VARCHAR e.g. '1'
    --   For multi-day weekly: comma-separated e.g. '1,3'
    --   For monthly: weekday number from <weekday> tag
    --   For yearly: derived from start_date
    -- dow_name: human-readable equivalent e.g. 'Monday' or 'Monday,Wednesday'
    -- -------------------------------------------------------------------------
    COALESCE(dow.recc_day_of_week_num, '') AS dow_number,
    COALESCE(
        CASE WHEN dow.recc_day_of_week_num IS NULL THEN NULL
            ELSE SUBSTRING(
                REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(
                    ',' + dow.recc_day_of_week_num + ',',
                    ',0,', ',Sunday,'),
                    ',1,', ',Monday,'),
                    ',2,', ',Tuesday,'),
                    ',3,', ',Wednesday,'),
                    ',4,', ',Thursday,'),
                    ',5,', ',Friday,'),
                    ',6,', ',Saturday,'),
                2,
                LEN(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(
                    ',' + dow.recc_day_of_week_num + ',',
                    ',0,', ',Sunday,'),
                    ',1,', ',Monday,'),
                    ',2,', ',Tuesday,'),
                    ',3,', ',Wednesday,'),
                    ',4,', ',Thursday,'),
                    ',5,', ',Friday,'),
                    ',6,', ',Saturday,')) - 2)
        END,
    '') AS dow_name,

    -- -------------------------------------------------------------------------
    -- WEEK NUMBER
    -- week_number: the week position within the recurrence pattern
    --   Weekly:                4-week cycle position anchored to 19 May 2025 (1-4)
    --   Monthly - Week Pattern: <weekdef> value from XML (1=1st, 2=2nd, 3=3rd, 4=4th week of month)
    --   Monthly - Fixed Date:  week-of-month derived from start_date day number
    --   Yearly:                week-of-month derived from start_date day number
    -- -------------------------------------------------------------------------
    wnum.recc_week_number,

    -- -------------------------------------------------------------------------
    -- START DATE & VALIDITY
    -- start_date: extracted from <start>MM/DD/YYYY</start> in recurrence XML
    -- is_valid_start_date: whether the start date correctly aligns with the recurrence pattern
    --   Weekly:                start_date DOW <= scheduled <days> value
    --   Monthly - Fixed Date:  start_date day-of-month <= <day> value
    --   Monthly - Week Pattern: start_date <= computed date of Nth weekday in start month
    --   Yearly/Daily/Multi-Day: always Valid
    -- -------------------------------------------------------------------------
    sd.start_date,
    COALESCE(vld.is_valid, '') AS is_valid_start_date,

    -- -------------------------------------------------------------------------
    -- RECURRENCE MONTH
    -- Only populated for monthly frequency types
    -- If Valid: month name of start_date (e.g. 'September')
    -- If Invalid: month name of start_date + 1 month (e.g. 'October')
    -- Used in Excel patch to determine which month the recurrence should begin from
    -- -------------------------------------------------------------------------
    COALESCE(dmonth.drop_month, '') AS drop_month,

    -- -------------------------------------------------------------------------
    -- RECURRENCE WEEK
    -- Only populated for Weekly frequency type (not Monthly - Week Pattern)
    -- If Valid: current 4-week cycle position of start_date (1-4)
    -- If Invalid: cycle position advanced by 1 (wrapping 4 -> 1)
    -- Anchored to 19 May 2025 as Week 1
    -- Used in Excel patch to correct the start date for invalid weekly setups
    -- -------------------------------------------------------------------------
    COALESCE(dweek.drop_week, wnum.recc_week_number) AS drop_week

FROM 
    UniqueSetups AS s
LEFT JOIN 
    ProductAggregates AS pa ON s.msdyn_agreementbookingsetupid = pa.msdyn_agreementbookingsetup
LEFT JOIN 
    dbo.[msdyn_agreement] AS a ON s.msdyn_agreement = a.msdyn_agreementid
LEFT JOIN 
    [dbo].[msdyn_functionallocation] AS fl ON s.vel_functionallocation = fl.Id
LEFT JOIN gopt_division div ON div.[Option] = a.vel_division
LEFT JOIN gopt_inv_freq inv_freq ON inv_freq.[Option] = a.vel_invoicingfrequency
LEFT JOIN 
    UniqueBranchTerritory AS bt 
        ON fl.vel_territory = bt.vel_territory 
        AND a.vel_division = bt.vel_division
        AND bt.rn = 1
LEFT JOIN
    BranchTimezone AS tz
        ON tz.msdyn_organizationalunitid = s.vel_branch


-- -------------------------------------------------------------------------
-- CROSS APPLY: pos
-- Finds character positions of key recurrence type tags in the XML string
-- Also counts <days> tag occurrences to detect multi-day weekly patterns
-- -------------------------------------------------------------------------
CROSS APPLY (
    SELECT
        CHARINDEX('<weeks',        s.msdyn_recurrencesettings) AS weeks_pos,
        CHARINDEX('<months',       s.msdyn_recurrencesettings) AS months_pos,
        CHARINDEX('<years',        s.msdyn_recurrencesettings) AS years_pos,
        CHARINDEX('<period>daily', s.msdyn_recurrencesettings) AS daily_pos,
        -- Count of <days> tags — >1 means multi-day weekly
        (LEN(s.msdyn_recurrencesettings) - LEN(REPLACE(s.msdyn_recurrencesettings, '<days>', ''))) / LEN('<days>') AS days_tag_count
) pos

-- -------------------------------------------------------------------------
-- CROSS APPLY: epos
-- Finds position of every=' attribute within the weeks/months tag
-- Scoped to start from the tag position to avoid false matches
-- -------------------------------------------------------------------------
CROSS APPLY (
    SELECT
        CHARINDEX('every=''', s.msdyn_recurrencesettings, pos.weeks_pos)  AS weeks_every_pos,
        CHARINDEX('every=''', s.msdyn_recurrencesettings, pos.months_pos) AS months_every_pos,
        CHARINDEX('every=''', s.msdyn_recurrencesettings, pos.daily_pos)  AS daily_every_pos
) epos

-- -------------------------------------------------------------------------
-- CROSS APPLY: cpos
-- Finds the closing quote of the every='N' attribute value
-- Used to extract the N value via SUBSTRING
-- -------------------------------------------------------------------------
CROSS APPLY (
    SELECT
        CHARINDEX('''', s.msdyn_recurrencesettings, epos.weeks_every_pos  + 7) AS weeks_close_pos,
        CHARINDEX('''', s.msdyn_recurrencesettings, epos.months_every_pos + 7) AS months_close_pos,
        CHARINDEX('''', s.msdyn_recurrencesettings, epos.daily_every_pos  + 7) AS daily_close_pos
) cpos

-- -------------------------------------------------------------------------
-- CROSS APPLY: freq
-- Calculates services_per_year based on recurrence type and interval
--   Yearly:             1
--   Daily:              365
--   Weekly (N):         52 / N * days_tag_count (multi-day multiplier)
--   Monthly (N):        12 / N
-- -------------------------------------------------------------------------
CROSS APPLY (
    SELECT ROUND(CASE
        WHEN pos.years_pos  > 0 THEN CAST(1 AS FLOAT)
        WHEN pos.daily_pos  > 0 THEN 365.0
        WHEN pos.weeks_pos  > 0 AND epos.weeks_every_pos > 0 AND cpos.weeks_close_pos > epos.weeks_every_pos + 7
            THEN (52.0 / CAST(SUBSTRING(s.msdyn_recurrencesettings, epos.weeks_every_pos + 7, cpos.weeks_close_pos - epos.weeks_every_pos - 7) AS FLOAT))
                 * pos.days_tag_count
        WHEN pos.months_pos > 0 AND epos.months_every_pos > 0 AND cpos.months_close_pos > epos.months_every_pos + 7
            THEN 12.0 / CAST(SUBSTRING(s.msdyn_recurrencesettings, epos.months_every_pos + 7, cpos.months_close_pos - epos.months_every_pos - 7) AS FLOAT)
        ELSE NULL
    END, 2) AS services_per_year
) freq

-- -------------------------------------------------------------------------
-- CROSS APPLY: spos
-- Finds position of <start> tag in recurrence XML
-- -------------------------------------------------------------------------
CROSS APPLY (
    SELECT
        CHARINDEX('<start>', s.msdyn_recurrencesettings) AS start_tag_pos
) spos

CROSS APPLY (
    SELECT
        CASE
            WHEN pos.years_pos  > 0 THEN 'Yearly'
            WHEN pos.daily_pos  > 0 AND epos.daily_every_pos > 0 AND cpos.daily_close_pos > epos.daily_every_pos + 7
                THEN SUBSTRING(s.msdyn_recurrencesettings, epos.daily_every_pos + 7, cpos.daily_close_pos - epos.daily_every_pos - 7) + ' Daily'
            WHEN pos.weeks_pos  > 0 AND epos.weeks_every_pos  > 0 AND cpos.weeks_close_pos  > epos.weeks_every_pos  + 7
                THEN SUBSTRING(s.msdyn_recurrencesettings, epos.weeks_every_pos  + 7, cpos.weeks_close_pos  - epos.weeks_every_pos  - 7) + ' Weekly'
            WHEN pos.months_pos > 0 AND epos.months_every_pos > 0 AND cpos.months_close_pos > epos.months_every_pos + 7
                THEN SUBSTRING(s.msdyn_recurrencesettings, epos.months_every_pos + 7, cpos.months_close_pos - epos.months_every_pos - 7) + ' Monthly'
            ELSE NULL
        END AS recurrence_frequency

) recc_freq

CROSS APPLY (
    SELECT
        CASE
            WHEN pos.years_pos  > 0 THEN 1
            WHEN pos.daily_pos  > 0 AND epos.daily_every_pos > 0 AND cpos.daily_close_pos > epos.daily_every_pos + 7
                THEN SUBSTRING(s.msdyn_recurrencesettings, epos.daily_every_pos + 7, cpos.daily_close_pos - epos.daily_every_pos - 7)
            WHEN pos.weeks_pos  > 0 AND epos.weeks_every_pos  > 0 AND cpos.weeks_close_pos  > epos.weeks_every_pos  + 7
                THEN SUBSTRING(s.msdyn_recurrencesettings, epos.weeks_every_pos  + 7, cpos.weeks_close_pos  - epos.weeks_every_pos  - 7)
            WHEN pos.months_pos > 0 AND epos.months_every_pos > 0 AND cpos.months_close_pos > epos.months_every_pos + 7
                THEN SUBSTRING(s.msdyn_recurrencesettings, epos.months_every_pos + 7, cpos.months_close_pos - epos.months_every_pos - 7)
            ELSE NULL
        END AS num_recurrences

) num_recc

-- -------------------------------------------------------------------------
-- CROSS APPLY: sd
-- Extracts start_date from <start>MM/DD/YYYY</start> in recurrence XML
-- Parses MM/DD/YYYY format by extracting substrings positionally
-- TRY_CAST returns NULL for malformed dates rather than erroring
-- -------------------------------------------------------------------------
CROSS APPLY (
    SELECT
        CASE
            WHEN spos.start_tag_pos > 0
            THEN TRY_CAST(
                RIGHT(SUBSTRING(s.msdyn_recurrencesettings, spos.start_tag_pos + 7, 10), 4)   -- YYYY
                + '-' +
                LEFT(SUBSTRING(s.msdyn_recurrencesettings, spos.start_tag_pos + 7, 10), 2)    -- MM
                + '-' +
                SUBSTRING(SUBSTRING(s.msdyn_recurrencesettings, spos.start_tag_pos + 7, 10), 4, 2) -- DD
            AS DATE)
            ELSE NULL
        END AS start_date
) sd

-- -------------------------------------------------------------------------
-- CROSS APPLY: tpos
-- Finds positions of day-related tags within the recurrence XML
--   <weekday>  : day of week number (0=Sun..6=Sat) used in monthly/weekly patterns
--   <weekdef>  : week-of-month number (1-4) used in Monthly - Week Pattern
--   <days>     : day of week for weekly recurrences
--   <day>      : fixed day of month for monthly fixed-date recurrences
-- -------------------------------------------------------------------------
CROSS APPLY (
    SELECT
        CHARINDEX('<weekday>',  s.msdyn_recurrencesettings) AS weekday_pos,
        CHARINDEX('</weekday>', s.msdyn_recurrencesettings) AS weekday_close_pos,
        CHARINDEX('<weekdef>',  s.msdyn_recurrencesettings) AS weekdef_pos,
        CHARINDEX('</weekdef>', s.msdyn_recurrencesettings) AS weekdef_close_pos,
        CHARINDEX('<days>',     s.msdyn_recurrencesettings) AS days_pos,
        CHARINDEX('</days>',    s.msdyn_recurrencesettings) AS days_close_pos,
        CHARINDEX('<day>',      s.msdyn_recurrencesettings) AS day_pos,
        CHARINDEX('</day>',     s.msdyn_recurrencesettings) AS day_close_pos
) tpos

-- -------------------------------------------------------------------------
-- CROSS APPLY: dow
-- Extracts day-of-week number(s) from recurrence XML
-- For multi-day weekly: returns comma-separated list e.g. '1,3' (Mon, Wed)
-- For single weekly:    returns single value e.g. '1'
-- For monthly:          returns <weekday> value or derives from start_date
-- For yearly:           derives from start_date
-- For daily:            NULL (no specific DOW)
-- -------------------------------------------------------------------------
CROSS APPLY (
    SELECT 
        CASE
            WHEN pos.daily_pos > 0 THEN NULL
            -- Multi-day weekly: concatenate up to 4 <days> values
            WHEN pos.weeks_pos > 0 AND pos.days_tag_count > 1
                THEN SUBSTRING(s.msdyn_recurrencesettings, tpos.days_pos + 6, tpos.days_close_pos - tpos.days_pos - 6)
                    + CASE WHEN pos.days_tag_count >= 2 AND CHARINDEX('<days>', s.msdyn_recurrencesettings, tpos.days_pos + 1) > 0
                        THEN ',' + SUBSTRING(s.msdyn_recurrencesettings,
                            CHARINDEX('<days>', s.msdyn_recurrencesettings, tpos.days_pos + 1) + 6,
                            CHARINDEX('</days>', s.msdyn_recurrencesettings, CHARINDEX('<days>', s.msdyn_recurrencesettings, tpos.days_pos + 1)) - CHARINDEX('<days>', s.msdyn_recurrencesettings, tpos.days_pos + 1) - 6)
                        ELSE '' END
                    + CASE WHEN pos.days_tag_count >= 3 AND CHARINDEX('<days>', s.msdyn_recurrencesettings, CHARINDEX('<days>', s.msdyn_recurrencesettings, tpos.days_pos + 1) + 1) > 0
                        THEN ',' + SUBSTRING(s.msdyn_recurrencesettings,
                            CHARINDEX('<days>', s.msdyn_recurrencesettings, CHARINDEX('<days>', s.msdyn_recurrencesettings, tpos.days_pos + 1) + 1) + 6,
                            CHARINDEX('</days>', s.msdyn_recurrencesettings, CHARINDEX('<days>', s.msdyn_recurrencesettings, CHARINDEX('<days>', s.msdyn_recurrencesettings, tpos.days_pos + 1) + 1)) - CHARINDEX('<days>', s.msdyn_recurrencesettings, CHARINDEX('<days>', s.msdyn_recurrencesettings, tpos.days_pos + 1) + 1) - 6)
                        ELSE '' END
                    + CASE WHEN pos.days_tag_count >= 4 AND CHARINDEX('<days>', s.msdyn_recurrencesettings, CHARINDEX('<days>', s.msdyn_recurrencesettings, CHARINDEX('<days>', s.msdyn_recurrencesettings, tpos.days_pos + 1) + 1) + 1) > 0
                        THEN ',' + SUBSTRING(s.msdyn_recurrencesettings,
                            CHARINDEX('<days>', s.msdyn_recurrencesettings, CHARINDEX('<days>', s.msdyn_recurrencesettings, CHARINDEX('<days>', s.msdyn_recurrencesettings, tpos.days_pos + 1) + 1) + 1) + 6,
                            CHARINDEX('</days>', s.msdyn_recurrencesettings, CHARINDEX('<days>', s.msdyn_recurrencesettings, CHARINDEX('<days>', s.msdyn_recurrencesettings, CHARINDEX('<days>', s.msdyn_recurrencesettings, tpos.days_pos + 1) + 1) + 1)) - CHARINDEX('<days>', s.msdyn_recurrencesettings, CHARINDEX('<days>', s.msdyn_recurrencesettings, CHARINDEX('<days>', s.msdyn_recurrencesettings, tpos.days_pos + 1) + 1) + 1) - 6)
                        ELSE '' END
            -- Monthly: use <weekday> tag if present, else derive from start_date
            WHEN pos.months_pos > 0
                THEN CAST(CASE
                    WHEN tpos.weekday_pos > 0
                        THEN CAST(SUBSTRING(s.msdyn_recurrencesettings, tpos.weekday_pos + 9, tpos.weekday_close_pos - tpos.weekday_pos - 9) AS INT)
                    ELSE DATEPART(WEEKDAY, sd.start_date) - 1
                END AS VARCHAR)
            -- Single-day weekly: use <days> tag, fallback to <day>, fallback to <weekday>
            WHEN pos.weeks_pos > 0
                THEN CAST(CASE
                    WHEN tpos.days_pos > 0
                        THEN CAST(SUBSTRING(s.msdyn_recurrencesettings, tpos.days_pos + 6, tpos.days_close_pos - tpos.days_pos - 6) AS INT)
                    WHEN tpos.day_pos > 0
                        THEN CAST(SUBSTRING(s.msdyn_recurrencesettings, tpos.day_pos + 5, tpos.day_close_pos - tpos.day_pos - 5) AS INT)
                    WHEN tpos.weekday_pos > 0
                        THEN CAST(SUBSTRING(s.msdyn_recurrencesettings, tpos.weekday_pos + 9, tpos.weekday_close_pos - tpos.weekday_pos - 9) AS INT)
                    ELSE NULL
                END AS VARCHAR)
            -- Yearly: derive from start_date
            WHEN pos.years_pos > 0
                THEN CAST(DATEPART(WEEKDAY, sd.start_date) - 1 AS VARCHAR)
            ELSE NULL
        END AS recc_day_of_week_num
) dow

-- -------------------------------------------------------------------------
-- CROSS APPLY: ftype
-- Classifies frequency type based on recurrence XML structure
--   Yearly:              <years> tag present
--   Daily:               <period>daily tag present
--   Weekly - Multi Day:  <weeks> tag with multiple <days> tags,
--                        OR single <days> but another ABS at same FL has same
--                        product, every=1 weekly, different day (split schedule)
--   Weekly:              <weeks> tag, single day
--   Monthly - Week Pattern: <months> tag + <weekdef> tag (Nth weekday of month)
--   Monthly - Fixed Date:   <months> tag without <weekdef> (fixed day of month)
-- -------------------------------------------------------------------------
CROSS APPLY (
    SELECT CASE
        WHEN pos.years_pos  > 0 THEN 'Yearly'
        WHEN pos.daily_pos  > 0 THEN 'Daily'
        WHEN pos.weeks_pos  > 0 AND pos.days_tag_count > 1 THEN 'Weekly - Multi Day'
        WHEN pos.weeks_pos  > 0 AND (
            EXISTS (
                SELECT 1 
                FROM dbo.[msdyn_agreementbookingsetup] s2
                WHERE s2.vel_functionallocation = s.vel_functionallocation
                AND s2.msdyn_agreementbookingsetupid <> s.msdyn_agreementbookingsetupid
                AND s2.statuscode = 1
                AND s2.[vel_productnames] = s.[vel_productnames]
                AND CHARINDEX('<weeks every=''1''', s2.msdyn_recurrencesettings) > 0
                AND CHARINDEX('<weeks every=''1''', s.msdyn_recurrencesettings) > 0
                AND CHARINDEX('<days>', s2.msdyn_recurrencesettings) > 0
                AND SUBSTRING(s2.msdyn_recurrencesettings, 
                        CHARINDEX('<days>', s2.msdyn_recurrencesettings) + 6,
                        CHARINDEX('</days>', s2.msdyn_recurrencesettings) - CHARINDEX('<days>', s2.msdyn_recurrencesettings) - 6)
                    <>
                    SUBSTRING(s.msdyn_recurrencesettings,
                        CHARINDEX('<days>', s.msdyn_recurrencesettings) + 6,
                        CHARINDEX('</days>', s.msdyn_recurrencesettings) - CHARINDEX('<days>', s.msdyn_recurrencesettings) - 6)
            )
        ) THEN 'Weekly - Multi Day'
        WHEN pos.weeks_pos  > 0 THEN 'Weekly'
        WHEN pos.months_pos > 0 AND tpos.weekdef_pos > 0 THEN 'Monthly - Week Pattern'
        WHEN pos.months_pos > 0 THEN 'Monthly - Fixed Date'
        ELSE NULL
    END AS frequency_type
) ftype

-- -------------------------------------------------------------------------
-- CROSS APPLY: wnum
-- Calculates week_number — the week position within the recurrence pattern
--   Weekly:                4-week cycle position (1-4) anchored to 19 May 2025 as 'week 1'
--                          Formula: (((days since anchor / 7) % 4) + 4) % 4 + 1
--                          The +4 before second %4 handles negative values for dates before anchor
--   Monthly - Week Pattern: <weekdef> value directly from XML (1-4)
--   Monthly - Fixed Date:  (DAY(start_date) - 1) / 7 + 1 (week block of the month)
--   Yearly:                (DAY(start_date) - 1) / 7 + 1
-- -------------------------------------------------------------------------
CROSS APPLY (
    SELECT CASE
        WHEN ftype.frequency_type = 'Weekly' AND sd.start_date IS NOT NULL
            THEN (((DATEDIFF(DAY, '2025-05-19', sd.start_date) / 7) % 4) + 4) % 4 + 1
        WHEN ftype.frequency_type = 'Monthly - Week Pattern' AND tpos.weekdef_close_pos > tpos.weekdef_pos + 9
            THEN CAST(SUBSTRING(s.msdyn_recurrencesettings, tpos.weekdef_pos + 9, tpos.weekdef_close_pos - tpos.weekdef_pos - 9) AS INT)
        WHEN ftype.frequency_type = 'Monthly - Fixed Date' AND sd.start_date IS NOT NULL
            THEN (DAY(sd.start_date) - 1) / 7 + 1
        WHEN ftype.frequency_type = 'Yearly' AND sd.start_date IS NOT NULL
            THEN (DAY(sd.start_date) - 1) / 7 + 1
        ELSE NULL
    END AS recc_week_number
) wnum

-- -------------------------------------------------------------------------
-- CROSS APPLY: vld
-- Determines whether the start_date correctly aligns with the recurrence pattern
--
-- Weekly:
--   Valid if: DOW of start_date <= <days> value
--   e.g. start on Monday (1), scheduled Wednesday (3): 1 <= 3 = Valid
--
-- Monthly - Fixed Date:
--   Valid if: DAY(start_date) <= <day> value
--   e.g. start on 5th, scheduled 15th: 5 <= 15 = Valid
--
-- Monthly - Week Pattern:
--   Valid if: start_date <= computed date of Nth weekday in start month
--   Computes actual occurrence date:
--     1. Get 1st of start month
--     2. Find days to add to reach first target weekday: (target_dow - dow_of_1st + 7) % 7
--     3. Add (weekdef-1) * 7 to reach Nth occurrence
--   e.g. start = 01/11/2025 (Sat), 4th Tuesday: 4th Tue = 25/11/2025, 01/11 <= 25/11 = Valid
--
-- Yearly / Daily / Weekly - Multi Day: always Valid / inconsequential
-- -------------------------------------------------------------------------
CROSS APPLY (
    SELECT
        CASE
            WHEN ftype.frequency_type IN ('Yearly', 'Daily', 'Weekly - Multi Day')
                THEN 'Valid'
            WHEN ftype.frequency_type = 'Weekly' AND sd.start_date IS NOT NULL AND tpos.days_pos > 0 AND tpos.days_close_pos > tpos.days_pos + 6
                THEN CASE
                    WHEN (DATEPART(WEEKDAY, sd.start_date) - 1) <= CAST(SUBSTRING(s.msdyn_recurrencesettings, tpos.days_pos + 6, tpos.days_close_pos - tpos.days_pos - 6) AS INT)
                    THEN 'Valid' ELSE 'Invalid'
                END
            WHEN ftype.frequency_type = 'Monthly - Fixed Date' AND sd.start_date IS NOT NULL AND tpos.day_pos > 0 AND tpos.day_close_pos > tpos.day_pos + 5
                THEN CASE
                    WHEN DAY(sd.start_date) <= CAST(SUBSTRING(s.msdyn_recurrencesettings, tpos.day_pos + 5, tpos.day_close_pos - tpos.day_pos - 5) AS INT)
                    THEN 'Valid' ELSE 'Invalid'
                END
            WHEN ftype.frequency_type = 'Monthly - Week Pattern' AND sd.start_date IS NOT NULL AND tpos.weekdef_pos > 0 AND tpos.weekday_pos > 0
                THEN CASE
                    WHEN sd.start_date <=
                        DATEADD(DAY,
                            (
                                CAST(SUBSTRING(s.msdyn_recurrencesettings, tpos.weekday_pos + 9, tpos.weekday_close_pos - tpos.weekday_pos - 9) AS INT)
                                - (DATEPART(WEEKDAY, DATEFROMPARTS(YEAR(sd.start_date), MONTH(sd.start_date), 1)) - 1)
                                + 7
                            ) % 7
                            + (CAST(SUBSTRING(s.msdyn_recurrencesettings, tpos.weekdef_pos + 9, tpos.weekdef_close_pos - tpos.weekdef_pos - 9) AS INT) - 1) * 7,
                            DATEFROMPARTS(YEAR(sd.start_date), MONTH(sd.start_date), 1)
                        )
                    THEN 'Valid' ELSE 'Invalid'
                END
            ELSE NULL
        END AS is_valid
) vld

-- -------------------------------------------------------------------------
-- CROSS APPLY: rmonth
-- Derives the recurrence_month for monthly frequency types only
-- If Valid:   month name of start_date (e.g. 'September')
-- If Invalid: month name of start_date + 1 month (e.g. 'October')
-- NULL for Weekly, Yearly, Daily
-- Used in Excel patch to identify which month the recurrence should start from
-- -------------------------------------------------------------------------
CROSS APPLY (
    SELECT CASE
        WHEN ftype.frequency_type NOT IN ('Monthly - Fixed Date', 'Monthly - Week Pattern', 'Yearly') THEN 'N/A'
        WHEN recc_freq.recurrence_frequency = '1 Monthly' THEN 'N/A'
        WHEN recc_freq.recurrence_frequency = 'Yearly' THEN DATENAME(MONTH, sd.start_date)
        WHEN sd.start_date IS NULL THEN NULL
        WHEN vld.is_valid = 'Valid'
            THEN DATENAME(MONTH, sd.start_date)
        WHEN vld.is_valid = 'Invalid'
            THEN DATENAME(MONTH, DATEADD(MONTH, 1, sd.start_date))
        ELSE NULL
    END AS drop_month
) dmonth

-- -------------------------------------------------------------------------
-- CROSS APPLY: rweek
-- Derives the recurrence_week for Weekly frequency type only
-- Represents which week in the 4-week cycle this setup should be scheduled
-- If Valid:   current 4-week cycle position of start_date (1-4)
-- If Invalid: cycle position advanced by 1, wrapping 4 -> 1
--             Formula: (week_number % 4) + 1
-- NULL for all non-Weekly frequency types
-- Used in Excel patch to correct the start date for invalid weekly setups
-- Anchor: Week 1 = week of 19 May 2025
-- -------------------------------------------------------------------------
CROSS APPLY (
    SELECT CASE
        WHEN ftype.frequency_type = 'Weekly' AND wnum.recc_week_number IS NOT NULL
            THEN CASE
                WHEN vld.is_valid = 'Valid'
                    THEN wnum.recc_week_number
                WHEN vld.is_valid = 'Invalid'
                    THEN (wnum.recc_week_number % 4) + 1
                ELSE NULL
            END
        ELSE NULL
    END AS drop_week
) dweek

WHERE
    s.rn = 1 AND
    a.statuscode = 1 AND
    s.statuscode = 1 AND
    div.LocalizedLabel IN ('Commercial Pest', 'Hygiene', 'Strata and Real Estate');
GO


