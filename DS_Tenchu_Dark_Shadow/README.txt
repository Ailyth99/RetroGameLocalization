
File processing tools for NDS Tenchu Dark Shadow (TENCHU DARK SECRET)

bd1_tool
Used for unpacking and re-injecting modified files into .BD1 or .FARC files.

infobind_tool
Tool for processing infobind.bd1, which contains "Mission Description" textures. First use bd1_tool to unpack infobind.bd1, then convert unpacked NCGR+NCLR to PNG, support injecting to generate new NCGR, and finally re-inject into infobind.bd1.

NCRGNCLR2PNG
Used for processing infoninmuexpbind.bd1, which contains item description textures. Usage is similar to infobind_tool: first unpack bd1, convert to PNG, and support re-importing modified PNGs to generate new NCGR.