Preparation only; no simulation started.

The supervisor initially checked the PATH launcher instead of the original
runner's sumolib.checkBinary resolver. That launcher selected a different
packaged binary lacking its Xerces dependency. The supervisor was corrected
to use checkBinary with the same SUMO_HOME as the original runner. The working
SUMO_HOME/bin/sumo reports 1.20.0. No archive or simulator code was modified.
This directory is not an experiment result.
