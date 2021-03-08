"""
This script uses ffmpeg to get the timecodes
of the scenes from the video.

Author: Alkl58
Date: 05.03.2021
"""
import subprocess
import os
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot

class WorkerScene(QObject):
    """
    WorkerScene Class

    Signals
    ----------
    finished : emit a signal if work is finished
    """
    finished = pyqtSignal()
    @pyqtSlot()
    def run(self, video_input, threshold, splitting_output, ffmpeg_path):
        """
        Attributes
        ----------
        video_input : string - path of the video input file
        threshold : float as string - scene detection threshold
        splitting_output : string - path of the split.txt output
        ffmpeg_path : path to ffmpeg
        """
        cmd = '\u0022' + ffmpeg_path + '\u0022' + " -i " + '\u0022' + video_input + '\u0022' + " -hide_banner -loglevel 32 -filter_complex select=" + '\u0022' + "gt(scene\\," + threshold + "),select=eq(key\\,1),showinfo" + '\u0022' + " -an -f null -"
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,universal_newlines=True, shell=True)

        temp = []
        for line in process.stdout:
            if "pts_time:" in line:
                temp.append(line)

        joined = ''.join(temp).split()
        scenes = []
        for value in joined:
            if "pts_time:" in value:
                scenes.append(value[9:])

        # Delete splits.txt file to avoid conflicts from previous attempts
        if os.path.exists(splitting_output):
            os.remove(splitting_output)

        # Create / Open split.txt file
        out_file = open(splitting_output, "a")

        # FFmpeg Args
        previous_scene = "0.000"
        for time_stamp in scenes:
            out_file.write("-ss " + previous_scene + " -to  " + time_stamp + "\n")
            previous_scene = time_stamp
        # Add last seeking argument
        out_file.write("-ss " + previous_scene)
        out_file.close()
        self.finished.emit()
