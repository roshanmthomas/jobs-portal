# MapMyCareer NCR reference notes

The Global IoT Career Radar map update uses the public MapMyCareer NCR project as an architectural/design reference:
https://github.com/pra-labs/mapmycareer-ncr

Reference patterns applied in this static site:
- count-based map markers / clustering concept instead of only raw unlabelled dots;
- progressive geographic exploration with breadcrumbs and summary cards;
- consistent focus/selection behavior between map and the job feed;
- use location confidence carefully and do not label approximate region centers as exact office coordinates.

This project remains an independent static HTML/Leaflet site and does not copy the reference application's Next.js/React implementation. Region/state inference in a static dataset is approximate where normalized fields are absent.
