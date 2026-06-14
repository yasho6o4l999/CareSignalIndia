# KPI Catalog

| KPI | Definition | Grain | Owner | Limitation |
|---|---|---|---|---|
| Potentially At-Risk Members | Distinct active members whose city, chronic condition, and environmental rule match on the selected date | Date | Care operations | Prototype operational exposure, not clinical risk |
| At-Risk Percentage | Potentially at-risk members divided by active members in publication-approved cities | Date | Care operations | Denominator follows current synthetic snapshot |
| Contactable At-Risk Members | At-risk members with consent and outside outreach cooldown | Date | Outreach operations | Does not guarantee successful contact |
| High-Priority Members | At-risk members with priority score at least four | Date | Care operations | Priority is operational, not clinical |
| Highest-Burden City | City with the most potentially at-risk members | Date and city | Regional operations | Absolute count should be read with city percentage |
| Largest Outreach Gap | City with the most at-risk but currently non-contactable members | Date and city | Outreach operations | Gap combines consent and cooldown reasons |
| Dominant Risk Driver | Environmental condition affecting the most distinct members | Date and condition | Care operations | Members can appear under multiple risk drivers |
| Member Risk Lifecycle | New, continuing, escalated, or resolved exposure compared with the previous available date | Date and member-rule | Care operations | Uses retained forecast snapshots, not observed outcomes |

Every dashboard KPI displays a hover definition. Production governance should additionally assign approval
status, change history, and a clinical or operational review owner.
