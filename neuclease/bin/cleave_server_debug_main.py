#!/usr/bin/env python3
import sys
import neuclease.cleave_server

def main():
    _debug_mode = False
    ## DEBUG
    if len(sys.argv) == 1:
        _debug_mode = True
        import os
        log_dir = os.path.dirname(neuclease.__file__) + '/../logs'
        sys.argv += ["--merge-table", "/magnetic/workspace/neuclease/tiny-merge-table.npy",
                     "--mapping-file", "/magnetic/workspace/neuclease/tiny-mapping.npy",
                     "--primary-dvid-server", "emdata3:8900",
                     "--primary-uuid", "017a",
                     "--primary-labelmap-instance", "segmentation",
                     #"--suspend-before-launch",
                     "--log-dir", log_dir]

    neuclease.cleave_server.main(_debug_mode)

## Example requests:
"""
{"body-id": 673509195, "mesh-instance": "segmentation_meshes_tars", "port": 8900, "request-timestamp": "2018-05-10 13:40:56.117063", "seeds": {"1": [675222237], "2": [1266560684], "3": [1142805921], "5": [1329312351], "6": [1328298063], "7": [1264523335], "8": [1233488801, 1358310013], "9": [1357286646]}, "segmentation-instance": "segmentation", "server": "emdata3.int.janelia.org", "user": "bergs", "uuid": "017a"}
{"body-id": 5812980088, "mesh-instance": "segmentation_meshes_tars", "port": 8900, "request-timestamp": "2018-05-10 13:48:32.071343", "seeds": {"1": [299622182, 769164613], "2": [727964335], "3": [1290606913], "4": [485167093], "5": [769514136]}, "segmentation-instance": "segmentation", "server": "emdata3.int.janelia.org", "user": "bergs", "uuid": "017a"}
{"body-id": 5812980124, "mesh-instance": "segmentation_meshes_tars", "port": 8900, "request-timestamp": "2018-05-10 13:51:46.112896", "seeds": {"1": [391090531], "2": [453151532, 515221115, 515221301, 515557950, 515562175, 515562381, 515562454, 546597327, 577632049, 608330428, 608667239, 639701979, 639702027, 639702182, 670736831, 670736971, 670737150, 670737574]}, "segmentation-instance": "segmentation", "server": "emdata3.int.janelia.org", "user": "bergs", "uuid": "017a"}
{"body-id": 5812980898, "mesh-instance": "segmentation_meshes_tars", "port": 8900, "request-timestamp": "2018-05-10 13:54:00.042885", "seeds": {"1": [449551305], "2": [1261194539], "3": [1229822848], "4": [883458155, 883458603], "5": [790693775]}, "segmentation-instance": "segmentation", "server": "emdata3.int.janelia.org", "user": "bergs", "uuid": "017a"}
""" 
    
if __name__ == "__main__":
    main()
