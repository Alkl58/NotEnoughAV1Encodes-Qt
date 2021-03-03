#!/usr/bin/env python3
# This Python file uses the following encoding: utf-8

from PyQt5 import QtWidgets, uic, QtCore
from PyQt5.QtCore import QObject, QThread, pyqtSignal, pyqtSlot
from PyQt5.QtWidgets import QFileDialog, QMessageBox
from multiprocessing.dummy import Pool
from functools import partial
from subprocess import call
from os import path
from pathlib import Path
import os
import sys
import time
import subprocess
import asyncio
import platform
import psutil 
import json
import math

class Worker(QObject):
    finished = pyqtSignal()
    progress = pyqtSignal(int)
    @pyqtSlot()
    def run(self, poolSize, queueFirst, queueSecond):
        pool = Pool(poolSize)  # Sets the amount of workers
        for i, returncode in enumerate(pool.imap(partial(call, shell=True), queueFirst)):  # Multi Threaded Encoding
            self.progress.emit(i + 1)
        for i, returncode in enumerate(pool.imap(partial(call, shell=True), queueSecond)):  # Multi Threaded Encoding
            self.progress.emit(i + 1)
        self.finished.emit()

class WorkerSplitting(QObject):
    finished = pyqtSignal()
    @pyqtSlot()
    def run(self, videoInput, videoCodec, segTime, splittingOutput):
        subprocess.call(['ffmpeg', '-y','-i', videoInput, '-map_metadata', '-1', '-c:v'] + videoCodec + ['-f', 'segment', '-segment_time', segTime, splittingOutput])
        self.finished.emit()

class WorkerScene(QObject):
    finished = pyqtSignal()
    @pyqtSlot()
    def run(self, videoInput, threshold, splittingOutput):

        cmd="ffmpeg -i " + '\u0022' + videoInput + '\u0022' + " -hide_banner -loglevel 32 -filter_complex select=" + '\u0022' + "gt(scene\\," + threshold + "),select=eq(key\\,1),showinfo" + '\u0022' + " -an -f null -"
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
        if os.path.exists(splittingOutput):
            os.remove(splittingOutput)

        # Create / Open split.txt file
        f = open(splittingOutput, "a")

        # FFmpeg Args
        previousScene = "0.000"
        for timeStamp in scenes:
            f.write("-ss " + previousScene + " -to  " + timeStamp + "\n")
            previousScene = timeStamp
        # Add last seeking argument
        f.write("-ss " + previousScene)
        f.close()
        self.finished.emit()

class neav1e(QtWidgets.QMainWindow):

    videoInput = None
    videoOutput = None

    videoQueueFirstPass = []
    videoQueueSecondPass = []

    encoderSettings = None
    encoderOutput = None
    encoderOutputStats = None
    encoderPasses = None
    encoderPassOne = None
    encoderPassTwo = None
    pipeColorFMT = None
    filterCommand = None

    tempDir = os.path.join(os.path.dirname(__file__), ".temp")
    tempDirFileName = None

    def __init__(self):
        super(neav1e, self).__init__()
        pth = os.path.join(os.path.dirname(__file__), "form.ui")  # Set path ui
        uic.loadUi(pth, self)  # Load the .ui file
        self.setFixedWidth(1036)  # Set Window Width
        self.setFixedHeight(600)  # Set Window Height
        self.setWindowTitle("NotEnoughAV1Encodes-Qt")  # Set Window Title

        # Controls IO
        self.pushButtonOpenSource.clicked.connect(self.openVideoSource)
        self.pushButtonSaveTo.clicked.connect(self.setVideoDestination)

        # Controls Start / Stop
        self.pushButtonStart.clicked.connect(self.mainEntry)

        # Controls Splitting
        self.comboBoxSplittingMethod.currentIndexChanged.connect(self.splittingUI)
        self.checkBoxSplittingReencode.stateChanged.connect(self.splittingReencode)

        self.horizontalSliderQ.valueChanged.connect(self.setQSliderValue)
        self.horizontalSliderEncoderSpeed.valueChanged.connect(self.setSpeedSliderValue)
        self.comboBoxSplittingMethod.currentIndexChanged.connect(self.setSummarySplitting)

        # Controls Encoder
        self.comboBoxEncoder.currentIndexChanged.connect(self.setEncoderUI)
        self.comboBoxPasses.currentIndexChanged.connect(self.setEncoderPassRav1e)
        self.radioButtonVBR.toggled.connect(self.toggleVBRQ)

        # !!! CHANGE IN UI FILE !!!
        self.labelSplittingChunkLength.hide()
        self.spinBoxChunking.hide()
        self.checkBoxSplittingReencode.hide()
        self.comboBoxSplittingReencode.hide()

        # Set Worker Count ComobBox
        for i in range(1, psutil.cpu_count(logical = False) + 1):
            self.comboBoxWorkerCount.addItem(str(i))
        self.comboBoxWorkerCount.setCurrentIndex(int((psutil.cpu_count(logical = False) - 1) * 0.75))

        # Show the GUI
        self.show()  

    #  ═══════════════════════════════════════ UI Logic ═══════════════════════════════════════
    def toggleVBRQ(self, a):
        if a:
            self.horizontalSliderQ.setEnabled(False)
            self.spinBoxVBR.setEnabled(True)
        else:
            self.horizontalSliderQ.setEnabled(True)
            self.spinBoxVBR.setEnabled(False)


    def setEncoderPassRav1e(self, n):
        if n == 1 and self.comboBoxEncoder.currentIndex() == 1:
            self.comboBoxPasses.setCurrentIndex(0) # rav1e two pass still broken
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Warning)
            msg.setText("rav1e currently does not support 2pass encoding.")
            msg.setWindowTitle("Attention!")
            msg.exec()


    def setEncoderUI(self, n):
        if n == 0:
            self.horizontalSliderEncoderSpeed.setMaximum(9)
            self.horizontalSliderEncoderSpeed.setValue(5)
            self.horizontalSliderQ.setMaximum(63)
            self.horizontalSliderQ.setValue(28)
        elif n == 1:
            #rav1e
            self.horizontalSliderEncoderSpeed.setMaximum(10)
            self.horizontalSliderEncoderSpeed.setValue(6)
            self.horizontalSliderQ.setMaximum(255)
            self.horizontalSliderQ.setValue(100)
            self.comboBoxPasses.setCurrentIndex(0) # rav1e two pass still broken


    def setSummarySplitting(self):
        self.labelSummarySplitting.setText(str(self.comboBoxSplittingMethod.currentText()))

    def reportProgress(self, n):
        self.progressBar.setValue(n)

    def setQSliderValue(self):
        self.labelQ.setText(str(self.horizontalSliderQ.value()))

    def setSpeedSliderValue(self):
        self.labelSpeed.setText(str(self.horizontalSliderEncoderSpeed.value()))

    def splittingReencode(self):
        if self.checkBoxSplittingReencode.isChecked() == True:
            self.comboBoxSplittingReencode.setEnabled(True)
        else:
            self.comboBoxSplittingReencode.setEnabled(False)

    def splittingUI(self):
        index = self.comboBoxSplittingMethod.currentIndex()
        if index == 0: # FFmpeg Scene Detection
            self.doubleSpinBoxFFmpegSceneThreshold.show()
            self.labelSplittingThreshold.show()
            self.labelSplittingChunkLength.hide()
            self.spinBoxChunking.hide()
            self.checkBoxSplittingReencode.hide()
            self.comboBoxSplittingReencode.hide()
        elif index == 1: # Equal Chunking
            self.doubleSpinBoxFFmpegSceneThreshold.hide()
            self.labelSplittingThreshold.hide()
            self.labelSplittingChunkLength.show()
            self.spinBoxChunking.show()
            self.checkBoxSplittingReencode.show()
            self.comboBoxSplittingReencode.show()

    def openVideoSource(self):
        fname, _ = QFileDialog.getOpenFileName(self, 'Select Video File', '',"Video files (*.mp4 *.mkv *.flv *.mov)")
        self.labelVideoSource.setText(fname)
        self.videoInput = fname
        self.tempDirFileName = os.path.splitext(os.path.basename(fname))[0]

    def setVideoDestination(self):
        fname, _ = QFileDialog.getSaveFileName(self, 'Select Video Output', '',"Video files (*.webm *.mp4 *.mkv)")
        self.labelVideoDestination.setText(fname)
        self.videoOutput = fname

    #  ═══════════════════════════════════════ Splitting ══════════════════════════════════════

    def setVideoFilters(self):
        crop = self.groupBoxCrop.isChecked() == True
        resize = self.groupBoxResize.isChecked() == True
        deinterlace = self.groupBoxDeinterlace.isChecked() == True
        rotate = self.groupBoxRotate.isChecked() == True
        tempCounter = 0
        filterCommand = ""

        if crop or resize or deinterlace or rotate:
            filterCommand = " -vf "
            if crop:
                filterCommand += self.VideoCrop()
                tempCounter += 1
            if deinterlace:
                if tempCounter != 0:
                    filterCommand += ","
                filterCommand += self.VideoDeinterlace()
                tempCounter += 1
            if rotate:
                if tempCounter != 0:
                    filterCommand += ","
                filterCommand += self.VideoRotate()
                tempCounter += 1
            if resize:
                if tempCounter != 0:
                     filterCommand += ","
                filterCommand += self.VideoResize() # !!! Has to be last, else ffmpeg logic fails
        self.filterCommand = filterCommand

    def VideoCrop(self):
        if self.groupBoxCrop.isChecked() == True:
            widthNew = str(self.spinBoxFilterCropRight.value() + self.spinBoxFilterCropLeft.value())
            heightNew = str(self.spinBoxFilterCropTop.value() + self.spinBoxFilterCropBottom.value())
            return "crop=iw-" + widthNew + ":ih-" + heightNew + ":" + str(self.spinBoxCropLeft.value()) + ":" + str(self.spinBoxCropTop.value())
        else:
            return None  # Needs to be set, else it will crop if in the same instance it was active

    def VideoResize(self):
        if self.groupBoxResize.isChecked() == True:
            return "scale=" + str(self.spinBoxFilterResizeWidth.value()) + ":" + str(self.spinBoxFilterResizeHeight.value())
        else:
            return None

    def VideoDeinterlace(self):
        if self.groupBoxDeinterlace.isChecked() == True:
            return "yadif=" + self.comboBoxDeinterlace.currentText()
        else:
            return None

    def VideoRotate(self):
        if self.groupBoxRotate.isChecked() == True:
            if self.comboBoxRotate.currentIndex() == 0:
                return "transpose=1"
            elif self.comboBoxRotate.currentIndex() == 1:
                return "transpose=2"
            elif self.comboBoxRotate.currentIndex() == 2:
                return "transpose=2,transpose=2"
            else:
                return None # unimplemented

    #  ════════════════════════════════════════ Filters ═══════════════════════════════════════

    def splitting(self):
        # Create Temp Folder if not existant
        path = Path(os.path.join(self.tempDir, self.tempDirFileName, "Chunks"))
        path.mkdir(parents=True, exist_ok=True)
        # Select the correct splitting method
        currentIndex = self.comboBoxSplittingMethod.currentIndex()
        if currentIndex == 0:
            # FFmpeg Scene Detect
            self.labelStatus.setText("Status: Detecting Scenes")
            self.ffmpegSceneDetect()
        elif currentIndex == 1:
            # Equal Chunking
            self.labelStatus.setText("Status: Splitting")
            self.ffmpegChunking()

    def ffmpegChunking(self):
        videoCodec = [ ]
        # Set Splitting Parameters
        if self.checkBoxSplittingReencode.isChecked() == True:
            if self.comboBoxSplittingReencode.currentIndex() == 0:
                videoCodec = ['libx264', '-crf', '0', '-preset', 'ultrafast']
            elif self.comboBoxSplittingReencode.currentIndex() == 1:
                videoCodec = ['ffv1', '-level', '3', '-threads', '6', '-coder', '1', '-context', '1', '-g', '1', '-slicecrc', '0', '-slices', '4']
            elif self.comboBoxSplittingReencode.currentIndex() == 2:
                videoCodec = ['utvideo']
        else:
            videoCodec = ['copy']
        segTime = str(self.spinBoxChunking.value())
        splittingOutput = os.path.join(self.tempDir, self.tempDirFileName, "Chunks", "split%6d.mkv")

        # Create a QThread object
        self.threadSplitting = QThread()
        # Create a worker object
        self.workerSplitting = WorkerSplitting()
        # Move worker to the thread
        self.workerSplitting.moveToThread(self.threadSplitting)
        # Connect signals and slots
        self.threadSplitting.started.connect(partial(self.workerSplitting.run, self.videoInput, videoCodec, segTime, splittingOutput))
        self.workerSplitting.finished.connect(self.threadSplitting.quit)
        self.workerSplitting.finished.connect(self.ffmpegSplittingFinished)
        self.workerSplitting.finished.connect(self.workerSplitting.deleteLater)
        self.threadSplitting.finished.connect(self.threadSplitting.deleteLater)
        # Start the thread
        self.threadSplitting.start()

    def ffmpegSplittingFinished(self):
        self.setQueue()
        self.mainEncode()

    def ffmpegSceneDetect(self):
        threshold = str(self.doubleSpinBoxFFmpegSceneThreshold.value())
        splittingOutput = os.path.join(self.tempDir, self.tempDirFileName, "splits.txt")
        # Create a QThread object
        self.threadScene = QThread()
        # Create a worker object
        self.workerScene = WorkerScene()
        # Move worker to the thread
        self.workerScene.moveToThread(self.threadScene)
        # Connect signals and slots
        self.threadScene.started.connect(partial(self.workerScene.run, self.videoInput, threshold, splittingOutput))
        self.workerScene.finished.connect(self.threadScene.quit)
        self.workerScene.finished.connect(self.ffmpegSplittingFinished)
        self.workerScene.finished.connect(self.workerScene.deleteLater)
        self.threadScene.finished.connect(self.threadScene.deleteLater)
        # Start the thread
        self.threadScene.start()



    #  ═════════════════════════════════════════ Main ═════════════════════════════════════════
    def mainEntry(self):
        # Check if input and output is set
        if self.videoInput and self.videoOutput:
            self.progressBar.setValue(0)
            # Splitting
            self.splitting()
        else:
            print("Not Implemented")

    #  ══════════════════════════════════ Command Generator ═══════════════════════════════════
    def setPipeColorFMT(self):
        fmt = None
        space = self.comboBoxColorFormat.currentIndex()
        if space == 0:
            fmt = "yuv420p"
        elif space == 1:
            fmt = "yuv422p"
        elif space == 2:
            fmt = "yuv444p"
        depth = self.comboBoxBitDepth.currentIndex()
        if depth == 0:
            fmt += " -strict -1"
        elif depth == 1:
            fmt += "10le -strict -1"
        elif depth == 2:
            fmt += "12le -strict -1"
        self.pipeColorFMT = fmt

    def setEncoderSettings(self):
        encoder = self.comboBoxEncoder.currentIndex()
        fmt = self.comboBoxColorFormat.currentIndex()
        passes = self.comboBoxPasses.currentIndex()
        settings = None
        if encoder == 0: # aomenc
            if passes == 0:
                self.encoderPasses = " --passes=1 "
            elif passes == 1:
                self.encoderPasses = " --passes=2 "
                self.encoderPassOne = " --pass=1 "
                self.encoderPassTwo = " --pass=2 "
            self.encoderOutput = " --output="
            self.encoderOutputStats = " --fpf="
            settings = "aomenc - --bit-depth=" + self.comboBoxBitDepth.currentText()
            if fmt == 0: # Color Format
                settings += " --i420"
            elif fmt == 1:
                settings += " --i422"
            elif fmt == 2:
                settings += " --i444"
            settings += " --cpu-used=" + str(self.horizontalSliderEncoderSpeed.value())
            if self.radioButtonCQ.isChecked() == True:
                settings += " --end-usage=q --cq-level=" + str(self.horizontalSliderQ.value())
            elif self.radioButtonVBR.isChecked() == True:
                settings += " --end-usage=vbr --target-bitrate=" + str(self.spinBoxVBR.value())
        elif encoder == 1: # rav1e
            self.encoderOutput = " --output "
            self.encoderPasses = " " # rav1e still does not support 2pass encoding
            settings = "rav1e - --speed " + str(self.horizontalSliderEncoderSpeed.value())
            if self.radioButtonCQ.isChecked() == True:
                settings += " --quantizer " + str(self.horizontalSliderQ.value())
            elif self.radioButtonVBR.isChecked() == True:
                settings += " --bitrate " + str(self.spinBoxVBR.value())
            settings += " --threads 4 --tile-cols 2 --tile-rows 1"

        self.encoderSettings = settings


    def setQueue(self):
        # Clear Queue
        self.videoQueueFirstPass = []
        self.videoQueueSecondPass = []

        self.setVideoFilters()
        self.setPipeColorFMT()
        self.setEncoderSettings()

        passes = self.comboBoxPasses.currentIndex()
        currentIndex = self.comboBoxSplittingMethod.currentIndex()

        if currentIndex == 0:
            # FFmpeg Scene Detect
            with open(os.path.join(self.tempDir, self.tempDirFileName, "splits.txt")) as f:
                counter = 0
                for seekPoint in f:
                    outFileName = str(counter).zfill(6)
                    tempInputFile = '\u0022' + self.videoInput + '\u0022'
                    tempOutputFile = '\u0022' + os.path.join(self.tempDir, self.tempDirFileName, "Chunks", "split" + outFileName + ".ivf") + '\u0022'
                    if passes == 0:
                        self.videoQueueFirstPass.append("ffmpeg -i " + tempInputFile + " " + seekPoint.rstrip() + " -pix_fmt " + self.pipeColorFMT + " " + self.filterCommand + " -color_range 0 -vsync 0 -f yuv4mpegpipe - | " + self.encoderSettings + self.encoderPasses + self.encoderOutput + tempOutputFile)
                    elif passes == 1:
                        tempOutputFileLog = '\u0022' + os.path.join(self.tempDir, self.tempDirFileName, "Chunks", "split" + outFileName + ".stats") + '\u0022'
                        self.videoQueueFirstPass.append("ffmpeg -i " + tempInputFile + " " + seekPoint.rstrip() + " -pix_fmt " + self.pipeColorFMT + " " + self.filterCommand + " -color_range 0 -vsync 0 -f yuv4mpegpipe - | " + self.encoderSettings + self.encoderPasses + self.encoderPassOne + self.encoderOutput + "/dev/null " + self.encoderOutputStats + tempOutputFileLog)
                        self.videoQueueSecondPass.append("ffmpeg -i " + tempInputFile + " " + seekPoint.rstrip() + " -pix_fmt " + self.pipeColorFMT + " " + self.filterCommand + " -color_range 0 -vsync 0 -f yuv4mpegpipe - | " + self.encoderSettings + self.encoderPasses + self.encoderPassTwo + self.encoderOutput + tempOutputFile + self.encoderOutputStats + tempOutputFileLog)
                    counter += 1
        elif currentIndex == 1:
            # Equal Chunking
            files = os.listdir(os.path.join(self.tempDir, self.tempDirFileName, "Chunks"))
            # Iterate over all mkv files
            for file in files:
                if file.endswith(".mkv"):
                    tempInputFile = '\u0022' + os.path.join(self.tempDir, self.tempDirFileName, "Chunks", file) + '\u0022'
                    tempOutputFile = '\u0022' + os.path.join(self.tempDir, self.tempDirFileName, "Chunks", os.path.splitext(os.path.basename(str(file)))[0] + ".ivf") + '\u0022'
                    if passes == 0:
                        self.videoQueueFirstPass.append("ffmpeg -i " + tempInputFile + " -pix_fmt " + self.pipeColorFMT + " -color_range 0 -vsync 0 -f yuv4mpegpipe - | " + self.encoderSettings + self.encoderPasses + self.encoderOutput + tempOutputFile)
                    elif passes == 1:
                        tempOutputFileLog = '\u0022' + os.path.join(self.tempDir, self.tempDirFileName, "Chunks", os.path.splitext(os.path.basename(str(file)))[0] + ".stats") + '\u0022'
                        self.videoQueueFirstPass.append("ffmpeg -i " + tempInputFile + " -pix_fmt " + self.pipeColorFMT + " -color_range 0 -vsync 0 -f yuv4mpegpipe - | " + self.encoderSettings + self.encoderPasses + self.encoderPassOne + self.encoderOutput + "/dev/null " + self.encoderOutputStats + tempOutputFileLog)
                        self.videoQueueSecondPass.append("ffmpeg -i " + tempInputFile + " -pix_fmt " + self.pipeColorFMT + " -color_range 0 -vsync 0 -f yuv4mpegpipe - | " + self.encoderSettings + self.encoderPasses + self.encoderPassTwo + self.encoderOutput + tempOutputFile + self.encoderOutputStats + tempOutputFileLog)

    #  ═══════════════════════════════════════ Encoding ═══════════════════════════════════════
    def mainEncode(self):
        self.labelStatus.setText("Status: Encoding")

        poolSize = self.comboBoxWorkerCount.currentIndex() + 1
        queueOne = self.videoQueueFirstPass
        queueTwo = self.videoQueueSecondPass

        self.progressBar.setMaximum(len(queueOne) + len(queueTwo))

        # Create a QThread object
        self.thread = QThread()
        # Create a worker object
        self.worker = Worker()
        # Move worker to the thread
        self.worker.moveToThread(self.thread)
        # Connect signals and slots
        self.thread.started.connect(partial(self.worker.run, poolSize, queueOne, queueTwo))
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.workerFinished)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.worker.progress.connect(self.reportProgress)
        # Start the thread
        self.thread.start()

    def workerFinished(self):
        self.labelStatus.setText("Status: Muxing")
        self.mainMuxing()
        self.labelStatus.setText("Status: Finished")

    #  ════════════════════════════════════════ Muxing ════════════════════════════════════════
    def mainMuxing(self):
        # Creates the list file of all encoded chunks for ffmpeg concat
        files = os.listdir(os.path.join(self.tempDir, self.tempDirFileName, "Chunks"))
        f = open(os.path.join(self.tempDir, self.tempDirFileName, "Chunks", "mux.txt"), "a")
        sorted_files = sorted(files)
        for file in sorted_files:
            if file.endswith(".ivf"):
                tempInputFile = '\u0027' + os.path.join(self.tempDir, self.tempDirFileName, "Chunks", file) + '\u0027'
                f.write("file " + tempInputFile + "\n")
        f.close()

        subprocess.call(['ffmpeg', '-y','-f', 'concat', '-safe', '0', '-i', os.path.join(self.tempDir, self.tempDirFileName, "Chunks", "mux.txt"), '-c', 'copy', self.videoOutput])


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = neav1e()
    app.exec_()
