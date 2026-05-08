/****** Object:  View [pbi].[BA_AGBS_AllBranch]    Script Date: 24/04/2026 9:16:24 AM ******/
/****** Object:  View [pbi].[BA_AGBS_AllBranch]    Script Date: 17/04/2026 3:21:18 PM ******/

/****** Object:  View [pbi].[BA_AGBS_AllBranch]    Script Date: 6/04/2026 3:00:01 PM ******/
/****** Object:  View [pbi].[BA_AGBS_AllBranch]    Script Date: 2/04/2026 7:03:45 PM ******/




CREATE OR ALTER          VIEW [pbi].[BA_AGBS_AllBranch] AS

with WOID_AGBID as 

(


select distinct msdyn_workorder,
	   AGBP.msdyn_agreementbookingsetup

from msdyn_workorderproduct as WOP
left join msdyn_agreementbookingproduct as AGBP on AGBP.msdyn_agreementbookingproductid=WOP.[msdyn_agreementbookingproduct]

),

AGBS AS (
    SELECT 
        ABBR.booking_setup_id,
        ABBR.FL_id,
        ABBR.latitude,
        ABBR.longitude,
        AGWO.msdyn_workorderid,
        AGWO.msdyn_name AS WOName,
        AGWO.msdyn_systemstatusname,
        AGWO.vel_divisionname,
        AGWO.msdyn_completedon_local AS CompletedDate,
        (DAY(AGWO.msdyn_completedon_local) - 1) / 7 + 1 AS WeekOfMonth,
        CASE ((DATEPART(WEEKDAY, AGWO.msdyn_completedon_local) + @@DATEFIRST - 2) % 7) + 1 
            WHEN 1 THEN 'Monday'
            WHEN 2 THEN 'Tuesday'
            WHEN 3 THEN 'Wednesday'
            WHEN 4 THEN 'Thursday'
            WHEN 5 THEN 'Friday'
            WHEN 6 THEN 'Saturday'
            WHEN 7 THEN 'Sunday'
        END AS WeekDay,
        -- CompleteDatePattern: reflects actual completed day formatted consistently
        -- with Current Date Pattern logic in the final SELECT
        -- 1 Weekly: Every <actual completed DOW>
        -- Weekly - Multi Day: Every <scheduled dow_name from ABS>
        -- All others: <week of month>-<actual completed DOW>
        CASE
            WHEN ABBR.frequency_type = 'Weekly - Multi Day'
                THEN CONCAT('Every ', ABBR.dow_name)
            WHEN ABBR.recurrence_frequency = '1 Weekly'
                THEN CONCAT('Every ',
                    CASE ((DATEPART(WEEKDAY, AGWO.msdyn_completedon_local) + @@DATEFIRST - 2) % 7) + 1 
                        WHEN 1 THEN 'Monday'
                        WHEN 2 THEN 'Tuesday'
                        WHEN 3 THEN 'Wednesday'
                        WHEN 4 THEN 'Thursday'
                        WHEN 5 THEN 'Friday'
                        WHEN 6 THEN 'Saturday'
                        WHEN 7 THEN 'Sunday'
                    END)
            ELSE CONCAT(
                (DAY(AGWO.msdyn_completedon_local) - 1) / 7 + 1,
                '-',
                CASE ((DATEPART(WEEKDAY, AGWO.msdyn_completedon_local) + @@DATEFIRST - 2) % 7) + 1 
                    WHEN 1 THEN 'Monday'
                    WHEN 2 THEN 'Tuesday'
                    WHEN 3 THEN 'Wednesday'
                    WHEN 4 THEN 'Thursday'
                    WHEN 5 THEN 'Friday'
                    WHEN 6 THEN 'Saturday'
                    WHEN 7 THEN 'Sunday'
                END)
        END AS CompleteDatePattern,
        AGWO.tech_names,
        ABBR.products,
        ABBR.billing_account,
        ABBR.recurrence_frequency,
        ABBR.num_recurrences,
        ABBR.frequency_type,
        ABBR.services_per_year,
        COUNT(msdyn_workorderid) OVER (PARTITION BY ABBR.booking_setup_id + ' | ' + ABBR.FL_id) AS NoOfServices
    FROM pbi.AG_WorkOrde AS AGWO
    LEFT JOIN WOID_AGBID
        ON WOID_AGBID.msdyn_workorder = AGWO.msdyn_workorderid
    INNER JOIN dbo.agb_ABS_Export AS ABBR
        ON ABBR.booking_setup_id = WOID_AGBID.msdyn_agreementbookingsetup
    WHERE msdyn_systemstatusname IN ('Completed', 'Posted')
      AND AGWO.msdyn_completedon_local >= '2025-05-01 00:00:00.000'
      AND AGWO.msdyn_completedon_local < '2026-03-25 00:00:00.000'
      AND ABBR.booking_setup_id IS NOT NULL
),

PatternRating
as 

(

select FL_id,
       --AGBS.recurrence_frequency, --as MostServFreq,
       CompleteDatePattern,
	   count(distinct booking_setup_id) as NoOfAGBS,
	   count(CompleteDatePattern) NoOfPattern,
	   Dense_Rank() over ( partition by FL_id order by count(CompleteDatePattern)desc,CompleteDatePattern asc) as NoOfPatternRanking

from AGBS

group by FL_id,CompleteDatePattern
),


MostFrequentPattern -- most frequency by each FL

as 

(


select FL_id,
       CompleteDatePattern,
	   NoOfPattern
from PatternRating
where NoOfPatternRanking=1

),





TechnameByService

as
(

select booking_setup_id,
       tech_names,
       count(distinct msdyn_workorderid) as NoOfWO
	  

from AGBS

where tech_names is not null

group by booking_setup_id,tech_names

),



Techname_Ranking

as
(

select 
       booking_setup_id,
       tech_names,
       NoOfWO,
	   Rank() over (partition by booking_setup_id order by NoOfWO desc,tech_names) as MostTech

from TechnameByService



),


Techname_Mostserviced   ---most serviced tech by each bookingsetup

as 

(

select 

         TechnameByService.booking_setup_id,

       	   STRING_AGG(
	 concat( 
	   CAST(TechnameByService.NoOfWO AS NVARCHAR(MAX)),' service from ',
	   CAST(TechnameByService.tech_names AS NVARCHAR(MAX))
	        ),'  |  ' ) as Allservice,
	      
		  Techname_Ranking.tech_names
			   
from TechnameByService

left join Techname_Ranking on Techname_Ranking.booking_setup_id=TechnameByService.booking_setup_id

where MostTech=1 and Techname_Ranking.tech_names is not null

group by TechnameByService.booking_setup_id,Techname_Ranking.tech_names

)


select 
		A.[booking_setup_id] AS [%booking_setup_id],
      A.[FL_id] AS [%FL_id],
	  A.setup_branch AS [%setup_branch],
      A.[division],
      A.[service_branch],
      A.[billing_account],
      A.[FL_name],
      A.[fl_number],
      A.latitude,
      A.longitude,
      A.[address] AS [Address 1],
      A.[city],
      A.[pre_bookingflex] AS [%pre_bookingflex],
      A.[post_bookingflex] AS [%post_bookingflex],
      A.[timewindow_start] AS [%timewindow_start],
      A.[timewindow_end] AS [%timewindow_end],
      A.[setup_name] AS [setup name],
      A.[products],
      A.[setup_value],
      A.[setup_quantity],
      A.[recurrence_string] AS [%recurrence_string],
      A.[service_duration] AS [Current Duration],
	  '' AS [~New Duration],
      A.[recurrence_frequency] AS [Recurrence Frequency],
      A.[num_recurrences],
      A.[frequency_type] AS [%frequency_type],
      A.[dow_number] AS [%recc_dow_number],
      A.[recc_week_number] AS [%recc_week_number],
      A.[start_date] AS [%start_date],
      A.[is_valid_start_date] AS [%is_valid_start_date],
      COALESCE(A.[preferred_start_time], A.[timewindow_start]) AS [*pref_start_time],
      CASE 
          WHEN A.frequency_type = 'Weekly - Multi Day'
              THEN CONCAT('Every ', A.[dow_name])
          WHEN A.frequency_type = 'Weekly' AND A.num_recurrences = 1
              THEN CONCAT('Every ', A.[dow_name])
          ELSE CONCAT(A.[drop_week], '-', A.[dow_name])
      END AS [Current Date Pattern],
      MP.CompleteDatePattern AS [Serviced Date Pattern],
	  MP.NoOfPattern AS [%NoOfPattern],
	  '' AS [*New Date Pattern],
      A.[drop_month] AS [~Drop Month],
	  A.auto_generate_booking [*On AGB?],
	  A.[preferred_resource] AS [*Preferred Resource],
	  MT.tech_names AS [Most Serviced Tech],
	  MT.Allservice AS [Full History],
      A.[WO_summary],
	  BT.vel_branchcode
	  

from dbo.agb_ABS_Export as A

left join MostFrequentPattern as MP on MP.FL_id=A.FL_id

left join msdyn_organizationalunit as BT on BT.msdyn_organizationalunitid=A.branch_id

left join Techname_Mostserviced as MT on MT.booking_setup_id=A.booking_setup_id

--where A.service_branch='Melbourne Commercial Pest'  and A.division='Commercial Pest' 

GO


