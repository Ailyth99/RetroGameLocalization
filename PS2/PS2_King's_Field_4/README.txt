Used to convert KF4 .tmr font textures to PNG, with support for rebuilding TMR files from PNG.
Since TMR files contain two CLUTs, they effectively hold two different visual images.
Before using this, you need to unpack KF4.DAT using this tool: ToolsForKF4.
https://github.com/TheStolenBattenberg/ToolsForKFIV

KING'S FIELD IV TMR Font Tool
Usage:
  Extract: tmr_font_tool -e <in.tmr>
  Repack:  tmr_font_tool -r <L1.png> <L2.png> <out.tmr>