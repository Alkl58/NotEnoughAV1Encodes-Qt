#!/usr/bin/env python3
# This Python file uses the following encoding: utf-8

import os
import re
import sys
import json
import shutil
import webbrowser
import subprocess

from pathlib import Path
from shutil import which
from datetime import datetime
from functools import partial
from PyQt5 import QtWidgets, uic, QtGui
from PyQt5.QtCore import QThread, Qt
from PyQt5.QtWidgets import QFileDialog, QMessageBox, QInputDialog

import worker
import worker_splitting
import worker_progress
import worker_framecount
import worker_scene
import worker_audio

import psutil

class neav1e(QtWidgets.QMainWindow):

    video_input = None
    video_output = None

    encode_started = False
    encode_paused = False

    null_path = os.devnull

    audio_encoding = False

    video_queue_first_pass = []
    video_queue_second_pass = []

    encoder_settings = None
    encoder_output = None
    encoder_output_stats = None
    encoder_passes = None
    encoder_pass_one = None
    encoder_pass_two = None
    pipe_color_fmt = None
    filter_command = None
    total_frame_count = 0

    current_dir = os.path.dirname(os.path.abspath(__file__))
    tempDir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Temp")
    temp_dir_file_name = None
    recommended_worker_count = None

    # FFmpeg expects ISO 639-2 codes for languages https://en.wikipedia.org/wiki/List_of_ISO_639-2_codes
    # ComboBoxes will be filled with this dictionary
    audioLanguageDictionary = {
        "English":      "eng", "Bosnian":       "bos", "Bulgarian":     "bul", "Chinese":       "chi",
        "Czech":        "cze", "Greek":         "gre", "Estonian":      "est", "Persian":       "per",
        "Filipino":     "fil", "Finnish":       "fin", "French":        "fre", "Georgian":      "geo",
        "German":       "ger", "Croatian":      "hrv", "Hungarian":     "hun", "Indonesian":    "ind",
        "Icelandic":    "ice", "Italian":       "ita", "Japanese":      "jpn", "Korean":        "kor",
        "Latin":        "lat", "Latvian":       "lav", "Lithuanian":    "lit", "Dutch":         "nld",
        "Norwegian":    "nob", "Polish":        "pol", "Portuguese":    "por", "Russian":       "rus",
        "Slovak":       "slk", "Slovenian":     "slv", "Spanish":       "spa", "Serbian":       "srp",
        "Swedish":      "swe", "Thai":          "tha", "Turkish":       "tur", "Ukrainian":     "ukr",
        "Vietnamese":   "vie"
        }

    def __init__(self):
        super(neav1e, self).__init__()
        pth = os.path.join(os.path.dirname(__file__), "interface", "form.ui")  # Set path ui
        uic.loadUi(pth, self)  # Load the .ui file
        self.setFixedWidth(842)  # Set Window Width
        self.setFixedHeight(568)  # Set Window Height
        self.setWindowTitle("NotEnoughAV1Encodes-Qt")  # Set Window Title

        # Controls IO
        self.pushButtonOpenSource.clicked.connect(self.open_video_source)
        self.pushButtonSaveTo.clicked.connect(self.set_video_destination)        

        # Controls Start / Stop
        self.pushButtonStart.clicked.connect(self.main_entry)
        self.pushButtonPauseResume.clicked.connect(self.pause_resume_encode)

        # Controls Splitting
        self.comboBoxSplittingMethod.currentIndexChanged.connect(self.splitting_ui)
        self.checkBoxSplittingReencode.stateChanged.connect(self.splitting_reencode)

        self.horizontalSliderQ.valueChanged.connect(self.set_q_slider_value)
        self.horizontalSliderEncoderSpeed.valueChanged.connect(self.set_speed_slider_value)
        self.comboBoxSplittingMethod.currentIndexChanged.connect(self.set_summary_splitting)

        # Controls Encoder
        self.comboBoxEncoder.currentIndexChanged.connect(self.set_encoder_ui)
        self.comboBoxBitDepth.currentIndexChanged.connect(self.set_ui_bitdepth)
        self.comboBoxColorFormat.currentIndexChanged.connect(self.set_ui_color_format)
        self.comboBoxPasses.currentIndexChanged.connect(self.set_encoder_pass_rav1e)
        self.radioButtonVBR.toggled.connect(self.toggle_vbr_q)
        self.checkBoxAdvancedSettings.stateChanged.connect(self.toggle_advanced_settings)
        self.checkBoxAomencDenoise.stateChanged.connect(self.toggle_aomenc_denoise)
        self.checkBoxRav1eContentLight.stateChanged.connect(self.toggle_rav1e_content_light)

        # Custom Settings
        self.groupBoxCustomSettings.toggled.connect(self.toggle_custom_settings)

        # Preferences
        self.checkBoxDeleteTempFiles.stateChanged.connect(self.save_preferences)
        self.checkBoxPixelAutoDetect.stateChanged.connect(self.save_preferences)
        self.checkBoxLogging.stateChanged.connect(self.save_preferences)
        self.pushButtonGithub.clicked.connect(self.open_github)

        # Preset
        self.pushButtonSaveNewPreset.clicked.connect(self.save_new_preset)
        self.pushButtonDeletePreset.clicked.connect(self.delete_preset)
        self.pushButtonLoadPreset.clicked.connect(self.load_preset)
        self.pushButtonSetDefaultPreset.clicked.connect(self.save_preferences)

        self.load_preset_startup()
        self.load_preferences()

        # !!! CHANGE IN UI FILE !!!
        self.labelSplittingChunkLength.hide()
        self.spinBoxChunking.hide()
        self.checkBoxSplittingReencode.hide()
        self.comboBoxSplittingReencode.hide()
        self.groupBoxAom.show()
        self.groupBoxRav1e.hide()
        self.groupBoxSvtav1.hide()

        self.tabWidget.setTabEnabled(4, False)

        # Set Worker Count ComobBox
        for i in range(1, psutil.cpu_count(logical = False) + 1):
            self.comboBoxWorkerCount.addItem(str(i))
        self.comboBoxWorkerCount.setCurrentIndex(int((psutil.cpu_count(logical = False) - 1) * 0.75))
        self.recommended_worker_count = int((psutil.cpu_count(logical = False) - 1) * 0.75)

        self.fill_audio_language()

        # Check if FFmpeg is in Path
        if which("ffmpeg") is None:
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Critical)
            msg.setText("FFmpeg not found in PATH!")
            msg.setWindowTitle("Error")
            msg.exec()
            # Exit Program
            sys.exit()

        self.first_time_startup()

        # Show the GUI
        self.show()

    def save_to_log(self, text):
        if self.checkBoxLogging.isChecked():
            out_path = Path(os.path.join(self.current_dir, "Logs"))
            out_path.mkdir(parents=True, exist_ok=True)
            now = datetime.now()
            with open(os.path.join(self.current_dir, "Logs", self.temp_dir_file_name + ".log"), 'a') as the_file:
                the_file.write(str(now) + " " + str(text) + '\n')

    #  ═════════════════════════════════════════ Audio ════════════════════════════════════════

    def encode_audio(self):
        command = ""
        if self.groupBoxTrackOne.isChecked():
            command += self.audio_cmd_generator("0", self.comboBoxTrackOneCodec.currentText(), str(self.spinBoxTrackOneBitrate.value()), self.switch_audio_channel_layout(str(self.comboBoxTrackOneLayout.currentIndex())), self.switch_audio_language(self.comboBoxTrackOneLanguage.currentText()))
        if self.groupBoxTrackTwo.isChecked():
            command += self.audio_cmd_generator("1", self.comboBoxTrackTwoCodec.currentText(), str(self.spinBoxTrackTwoBitrate.value()), self.switch_audio_channel_layout(str(self.comboBoxTrackTwoLayout.currentIndex())), self.switch_audio_language(self.comboBoxTrackTwoLanguage.currentText()))
        if self.groupBoxTrackThree.isChecked():
            command += self.audio_cmd_generator("2", self.comboBoxTrackThreeCodec.currentText(), str(self.spinBoxTrackThreeBitrate.value()), self.switch_audio_channel_layout(str(self.comboBoxTrackThreeLayout.currentIndex())), self.switch_audio_language(self.comboBoxTrackThreeLanguage.currentText()))
        if self.groupBoxTrackThree.isChecked():
            command += self.audio_cmd_generator("3", self.comboBoxTrackFourCodec.currentText(), str(self.spinBoxTrackFourBitrate.value()), self.switch_audio_channel_layout(str(self.comboBoxTrackFourLayout.currentIndex())), self.switch_audio_language(self.comboBoxTrackFourLanguage.currentText()))
        command += " -af aformat=channel_layouts=" + '\u0022' + "7.1|5.1|stereo|mono" + '\u0022'
        self.save_to_log(command)
        if self.groupBoxTrackOne.isChecked() or self.groupBoxTrackTwo.isChecked() or self.groupBoxTrackThree.isChecked() or self.groupBoxTrackThree.isChecked():
            out_path = Path(os.path.join(self.tempDir, self.temp_dir_file_name, "Audio"))
            out_path.mkdir(parents=True, exist_ok=True)
            audio_output = os.path.join(self.tempDir, self.temp_dir_file_name, "Audio", "audio.mkv")
            self.audio_encoding = True
            # Create a QThread object
            self.thread_encode_audio = QThread()
            # Create a worker object
            self.worker_encode_audio = worker_audio.WorkerAudio()
            # Move worker to the thread
            self.worker_encode_audio.moveToThread(self.thread_encode_audio)
            # Connect signals and slots
            self.thread_encode_audio.started.connect(partial(self.worker_encode_audio.run, self.video_input, command, audio_output))
            self.worker_encode_audio.finished.connect(self.thread_encode_audio.quit)
            self.worker_encode_audio.finished.connect(self.splitting)
            self.worker_encode_audio.finished.connect(self.worker_encode_audio.deleteLater)
            self.thread_encode_audio.finished.connect(self.thread_encode_audio.deleteLater)
            # Start the thread
            self.thread_encode_audio.start()
        else:
            self.audio_encoding = False
            self.splitting()

    def audio_cmd_generator(self, activetrackindex, audiocodec, activetrackbitrate, channellayout, lang):
        # Audio Mapping
        audio = '-map 0:a:' + activetrackindex + ' -c:a:' + activetrackindex
        # Codec
        audio += self.switch_audio_codec(audiocodec)
        # Channel Layout / Bitrate
        audio += ' -b:a:' + activetrackindex + ' ' + activetrackbitrate + 'k'
        audio += ' -ac:a:' + activetrackindex + ' ' + channellayout
        # Metadata
        audio += ' -metadata:s:a:' + activetrackindex + ' language=' + lang
        audio += ' -metadata:s:a:' + activetrackindex + ' title=' + '\u0022' + '[' + lang.upper() + '] ' + audiocodec + ' ' + activetrackbitrate + 'kbps' + '\u0022'
        return audio

    def switch_audio_language(self, lang):
        return self.audioLanguageDictionary[lang]

    def switch_audio_codec(self, codec):
        value = ""
        if codec == "Opus":
            value = ' libopus'
        elif codec == "AC3":
            value = ' ac3'
        elif codec == "AAC":
            value = ' aac'
        elif codec == "MP3":
            value = ' libmp3lame'
        return value

    def switch_audio_channel_layout(self, layout):
        value = ""
        if layout == "0":
            value = '1'
        elif layout == "1":
            value = '2'
        elif layout == "3":
            value = '6'
        elif layout == "4":
            value = '8'
        return value

    def ffprobe_audio_detect(self):
        cmd="ffprobe -i " + '\u0022' + self.video_input + '\u0022' + " -loglevel error -select_streams a -show_entries stream=index -of csv=p=1"
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,universal_newlines=True, shell=True)

        temp = []
        for line in process.stdout:
            temp.append(line)
        joined = ''.join(temp).split()

        counter = 0
        track_one = track_two = track_three = track_four = False
        for _ in joined:
            if counter == 0:
                track_one = True
            if counter == 1:
                track_two = True
            if counter == 2:
                track_three = True
            if counter == 3:
                track_four = True
            counter += 1

        self.groupBoxTrackOne.setEnabled(track_one)
        self.groupBoxTrackOne.setChecked(track_one)
        self.groupBoxTrackTwo.setEnabled(track_two)
        self.groupBoxTrackTwo.setChecked(track_two)
        self.groupBoxTrackThree.setEnabled(track_three)
        self.groupBoxTrackThree.setChecked(track_three)
        self.groupBoxTrackFour.setEnabled(track_four)
        self.groupBoxTrackFour.setChecked(track_four)

    #  ═══════════════════════════════════════ UI Logic ═══════════════════════════════════════

    def pause_resume_encode(self):
        if self.encode_paused is False:
            self.pause_ffmpeg()
            self.encode_paused = True
            self.labelStatus.setText("Status: Paused")
            self.pushButtonPauseResume.setIcon(QtGui.QIcon('img/resume.png'))
        else:
            self.resume_ffmpeg()
            self.encode_paused = False
            self.pushButtonPauseResume.setIcon(QtGui.QIcon('img/stop.png'))

    def set_ui_color_format(self):
        self.labelSummaryColorFormat.setText(self.comboBoxColorFormat.currentText())

    def set_ui_bitdepth(self):
        self.labelSummaryBitdepth.setText(self.comboBoxBitDepth.currentText())

    def ffprobe_pixel_format_detect(self):
        cmd="ffprobe -i " + '\u0022' + self.video_input + '\u0022' + " -v error -select_streams v -of default=noprint_wrappers=1:nokey=1 -show_entries stream=pix_fmt"
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,universal_newlines=True, shell=True)
        temp = []
        for line in process.stdout:
            temp.append(line)

        yuv420p = bool(re.search("^yuv420p", temp[0].strip("\n")))
        yuv422p = bool(re.search("^yuv422p", temp[0].strip("\n")))
        yuv444p = bool(re.search("^yuv444p", temp[0].strip("\n")))
        le10 = bool(re.search("10le$", temp[0].strip("\n")))
        le12 = bool(re.search("12le$", temp[0].strip("\n")))

        if yuv420p:
            self.comboBoxColorFormat.setCurrentIndex(0)
        elif yuv422p:
            self.comboBoxColorFormat.setCurrentIndex(1)
        elif yuv444p:
            self.comboBoxColorFormat.setCurrentIndex(2)
        
        if le10:
            #10bit
            self.comboBoxBitDepth.setCurrentIndex(1)
        elif le12:
            #12bit
            self.comboBoxBitDepth.setCurrentIndex(2)
        else:
            #8bit
            self.comboBoxBitDepth.setCurrentIndex(0)

    def first_time_startup_dependencie_check(self):
        ffmpeg_found = which("ffmpeg") is not None
        ffprobe_found = which("ffprobe") is not None
        aomenc_found = which("aomenc") is not None
        rav1e_found = which("rav1e") is not None
        svt_av1_found = which("SvtAv1EncApp") is not None
        text = "ffmpeg found? : " + str(ffmpeg_found)
        text += "\nffprobe found? : " + str(ffprobe_found)
        text += "\n__________________"
        text += "\naomenc found? : " + str(aomenc_found)
        text += "\nrav1e found? : " + str(rav1e_found)
        text += "\nsvt-av1 found? : " + str(svt_av1_found)
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Information)
        msg.setText(text)
        msg.setWindowTitle("Dependency Check")
        msg.exec()

    def first_time_startup(self):
        if os.path.isfile(os.path.join(self.current_dir, "preferences.json")) is False:
            text = "Please read before continuing:"
            text += "\n➔ You can pause and resume the encoding process"
            text += "\n➔ Using too many workers can result in a laggy Desktop"
            text += "\n➔ It is recommended to test first with small samples"
            text += "\n➔ This software is licensed under GNU GPL v3.0"
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Information)
            msg.setText(text)
            msg.setWindowTitle("First Launch")
            msg.exec()
            self.first_time_startup_dependencie_check()
            self.save_preferences()

    def open_github(self):
        webbrowser.open('https://github.com/Alkl58/NotEnoughAV1Encodes-Qt', new=2)

    def fill_audio_language(self):
        # Clears Audio Language ComboBox & fills it with the dictionary
        self.comboBoxTrackOneLanguage.clear()
        self.comboBoxTrackTwoLanguage.clear()
        self.comboBoxTrackThreeLanguage.clear()
        self.comboBoxTrackFourLanguage.clear()
        for i in self.audioLanguageDictionary:
            self.comboBoxTrackOneLanguage.addItem(i)
            self.comboBoxTrackTwoLanguage.addItem(i)
            self.comboBoxTrackThreeLanguage.addItem(i)
            self.comboBoxTrackFourLanguage.addItem(i)

    def toggle_custom_settings(self):
        if self.groupBoxCustomSettings.isChecked():
            self.groupBoxAom.setEnabled(False)
            self.groupBoxRav1e.setEnabled(False)
            self.groupBoxSvtav1.setEnabled(False)
            self.set_encoder_settings()
            self.textEditCustomSettings.setPlainText(self.encoder_settings)
        else:
            self.groupBoxAom.setEnabled(True)
            self.groupBoxRav1e.setEnabled(True)
            self.groupBoxSvtav1.setEnabled(True)

    def toggle_rav1e_content_light(self):
        self.spinBoxRav1eCll.setEnabled(self.checkBoxRav1eContentLight.isChecked() is True)
        self.spinBoxRav1eFall.setEnabled(self.checkBoxRav1eContentLight.isChecked() is True)

    def toggle_aomenc_denoise(self):
        self.spinBoxAomencDenoise.setEnabled(self.checkBoxAomencDenoise.isChecked() is True)

    def toggle_advanced_settings(self):
        self.tabWidget.setTabEnabled(4, self.checkBoxAdvancedSettings.isChecked() is True)

    def toggle_vbr_q(self, signal):
        if signal:
            self.horizontalSliderQ.setEnabled(False)
            self.spinBoxVBR.setEnabled(True)
        else:
            self.horizontalSliderQ.setEnabled(True)
            self.spinBoxVBR.setEnabled(False)

    def set_encoder_pass_rav1e(self, passes):
        if passes == 1 and self.comboBoxEncoder.currentIndex() == 1:
            self.comboBoxPasses.setCurrentIndex(0) # rav1e two pass still broken
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Warning)
            msg.setText("rav1e currently does not support 2pass encoding.")
            msg.setWindowTitle("Attention!")
            msg.exec()

    def set_encoder_ui(self, encoder):
        self.set_summary_encoder()
        if encoder == 0:
            #aomenc
            self.horizontalSliderEncoderSpeed.setMaximum(9)
            self.horizontalSliderEncoderSpeed.setValue(5)
            self.horizontalSliderQ.setMaximum(63)
            self.horizontalSliderQ.setValue(28)
            self.comboBoxWorkerCount.setCurrentIndex(self.recommended_worker_count)
            self.groupBoxAom.show()
            self.groupBoxRav1e.hide()
            self.groupBoxSvtav1.hide()
        elif encoder == 1:
            #rav1e
            self.horizontalSliderEncoderSpeed.setMaximum(10)
            self.horizontalSliderEncoderSpeed.setValue(6)
            self.horizontalSliderQ.setMaximum(255)
            self.horizontalSliderQ.setValue(100)
            self.comboBoxWorkerCount.setCurrentIndex(self.recommended_worker_count)
            self.comboBoxPasses.setCurrentIndex(0) # rav1e two pass still broken
            self.groupBoxAom.hide()
            self.groupBoxRav1e.show()
            self.groupBoxSvtav1.hide()
        elif encoder == 2:
            #svt-av1
            self.horizontalSliderQ.setMaximum(63)
            self.horizontalSliderQ.setValue(28)
            self.horizontalSliderEncoderSpeed.setMaximum(8)
            self.horizontalSliderEncoderSpeed.setValue(5)
            self.comboBoxWorkerCount.setCurrentIndex(0)
            self.groupBoxAom.hide()
            self.groupBoxRav1e.hide()
            self.groupBoxSvtav1.show()

    def set_summary_splitting(self):
        self.labelSummarySplitting.setText(str(self.comboBoxSplittingMethod.currentText()))

    def set_summary_encoder(self):
        self.labelSummaryEncoder.setText(str(self.comboBoxEncoder.currentText()))

    def report_progress(self, signal):
        self.progressBar.setValue(signal)
        self.labelStatus.setText("Status: " + str(signal) + " / " + str(self.total_frame_count) + " Frames")

    def set_q_slider_value(self):
        self.labelQ.setText(str(self.horizontalSliderQ.value()))

    def set_speed_slider_value(self):
        self.labelSpeed.setText(str(self.horizontalSliderEncoderSpeed.value()))
        self.labelSummarySpeed.setText(str(self.horizontalSliderEncoderSpeed.value()))

    def splitting_reencode(self):
        if self.checkBoxSplittingReencode.isChecked() is True:
            self.comboBoxSplittingReencode.setEnabled(True)
        else:
            self.comboBoxSplittingReencode.setEnabled(False)

    def splitting_ui(self):
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

    def open_video_source(self):
        fname, _ = QFileDialog.getOpenFileName(self, 'Select Video File', '',"Video files (*.mp4 *.mkv *.flv *.mov)")
        if fname:
            self.labelVideoSource.setText(fname)
            self.video_input = fname
            self.temp_dir_file_name = os.path.splitext(os.path.basename(fname))[0]
            self.ffprobe_audio_detect()
            if self.checkBoxPixelAutoDetect.isChecked():
                self.ffprobe_pixel_format_detect()

    def set_video_destination(self):
        fname, _ = QFileDialog.getSaveFileName(self, 'Select Video Output', '',"Video files (*.webm *.mp4 *.mkv)")
        if fname:
            self.labelVideoDestination.setText(fname)
            self.video_output = fname

    def save_new_preset(self):
        text_preset, clicked_ok = QInputDialog.getText(self, 'Preset', 'Enter Preset Name')
        if clicked_ok and text_preset:
            self.save_preset(text_preset)

    #  ═════════════════════════════════════════ Preset ═══════════════════════════════════════

    def load_preset(self):

        # The user could load a preset after loading a video file
        # The preset could potentially toggle the audio, even if not available
        temp_track_one = self.groupBoxTrackOne.isEnabled()
        temp_track_two = self.groupBoxTrackTwo.isEnabled()
        temp_track_three = self.groupBoxTrackThree.isEnabled()
        temp_track_four = self.groupBoxTrackFour.isEnabled()

        if os.path.isfile(os.path.join(self.current_dir, 'Presets', self.comboBoxPresets.currentText() + '.json')):
            with open(os.path.join(self.current_dir, 'Presets', self.comboBoxPresets.currentText() + '.json')) as json_file:
                data = json.load(json_file)
                for p in data['settings']:
                    self.comboBoxSplittingMethod.setCurrentIndex(p['splitting_method'])
                    self.doubleSpinBoxFFmpegSceneThreshold.setValue(p['splitting_scene_threshold'])
                    self.spinBoxChunking.setValue(p['splitting_chunking_length'])
                    self.checkBoxSplittingReencode.setChecked(p['splitting_chunking_reencode'])
                    self.comboBoxSplittingReencode.setCurrentIndex(p['splitting_chunking_codec'])
                    self.comboBoxEncoder.setCurrentIndex(p['video_encoder'])
                    self.comboBoxBitDepth.setCurrentIndex(p['video_bit_depth'])
                    self.comboBoxColorFormat.setCurrentIndex(p['video_color_fmt'])
                    self.horizontalSliderEncoderSpeed.setValue(p['video_speed'])
                    self.comboBoxPasses.setCurrentIndex(p['video_passes'])
                    self.checkBoxAdvancedSettings.setChecked(p['video_advanced'])
                    self.radioButtonCQ.setChecked(p['video_q'])
                    self.radioButtonVBR.setChecked(p['video_vbr'])
                    self.horizontalSliderQ.setValue(p['video_q_amount'])
                    self.spinBoxVBR.setValue(p['video_vbr_amount'])
                    self.comboBoxWorkerCount.setCurrentIndex(p['worker_count'])
                for p in data['filters']:
                    self.groupBoxCrop.setChecked(p['filters_crop'])
                    self.spinBoxFilterCropTop.setValue(p['filters_crop_top'])
                    self.spinBoxFilterCropRight.setValue(p['filters_crop_right'])
                    self.spinBoxFilterCropBottom.setValue(p['filters_crop_bottom'])
                    self.spinBoxFilterCropLeft.setValue(p['filters_crop_left'])
                    self.groupBoxResize.setChecked(p['filters_resize'])
                    self.spinBoxFilterResizeWidth.setValue(p['filters_resize_width'])
                    self.spinBoxFilterResizeHeight.setValue(p['filters_resize_height'])
                    self.groupBoxRotate.setChecked(p['filters_rotate'])
                    self.comboBoxRotate.setCurrentIndex(p['filters_rotate_amount'])
                    self.groupBoxDeinterlace.setChecked(p['filters_deinterlace'])
                    self.comboBoxDeinterlace.setCurrentIndex(p['filters_deinterlace_type'])
                for p in data['audio']:
                    self.groupBoxTrackOne.setChecked(p['track_one'])
                    self.groupBoxTrackTwo.setChecked(p['track_two'])
                    self.groupBoxTrackThree.setChecked(p['track_three'])
                    self.groupBoxTrackFour.setChecked(p['track_four'])
                    self.comboBoxTrackOneCodec.setCurrentIndex(p['track_one_codec'])
                    self.comboBoxTrackTwoCodec.setCurrentIndex(p['track_two_codec'])
                    self.comboBoxTrackThreeCodec.setCurrentIndex(p['track_three_codec'])
                    self.comboBoxTrackFourCodec.setCurrentIndex(p['track_four_codec'])
                    self.spinBoxTrackOneBitrate.setValue(p['track_one_bitrate'])
                    self.spinBoxTrackTwoBitrate.setValue(p['track_two_bitrate'])
                    self.spinBoxTrackThreeBitrate.setValue(p['track_three_bitrate'])
                    self.spinBoxTrackFourBitrate.setValue(p['track_four_bitrate'])
                    self.comboBoxTrackOneLayout.setCurrentIndex(p['track_one_layout'])
                    self.comboBoxTrackTwoLayout.setCurrentIndex(p['track_two_layout'])
                    self.comboBoxTrackThreeLayout.setCurrentIndex(p['track_three_layout'])
                    self.comboBoxTrackFourLayout.setCurrentIndex(p['track_four_layout'])
                    self.comboBoxTrackOneLanguage.setCurrentIndex(p['track_one_language'])
                    self.comboBoxTrackTwoLanguage.setCurrentIndex(p['track_two_language'])
                    self.comboBoxTrackThreeLanguage.setCurrentIndex(p['track_three_language'])
                    self.comboBoxTrackFourLanguage.setCurrentIndex(p['track_four_language'])
                if temp_track_one is False:
                    self.groupBoxTrackOne.setEnabled(False)
                    self.groupBoxTrackOne.setChecked(False)
                if temp_track_two is False:
                    self.groupBoxTrackTwo.setEnabled(False)
                    self.groupBoxTrackTwo.setChecked(False)
                if temp_track_three is False:
                    self.groupBoxTrackThree.setEnabled(False)
                    self.groupBoxTrackThree.setChecked(False)
                if temp_track_four is False:
                    self.groupBoxTrackFour.setEnabled(False)
                    self.groupBoxTrackFour.setChecked(False)

                if self.checkBoxAdvancedSettings.isChecked():
                    for p in data['advanced_settings']:
                        self.groupBoxCustomSettings.setChecked(True)
                        self.textEditCustomSettings.setPlainText(p['command_line'])

    def delete_preset(self):
        if os.path.isfile(os.path.join(self.current_dir, 'Presets', self.comboBoxPresets.currentText() + '.json')):
            os.remove(os.path.join(self.current_dir, 'Presets', self.comboBoxPresets.currentText() + '.json'))
            self.comboBoxPresets.clear()
            self.load_preset_startup()

    def load_preset_startup(self):
        if os.path.exists(os.path.join(self.current_dir, "Presets")):
            files = os.listdir(os.path.join(self.current_dir, "Presets"))
            for file in files:
                if file.endswith(".json"):
                    self.comboBoxPresets.addItem(os.path.splitext(os.path.basename(file))[0])

    def save_preset(self, preset_name):
        # Create Preset Folder if not existant
        out_path = Path(os.path.join(self.current_dir, "Presets"))
        out_path.mkdir(parents=True, exist_ok=True)

        save_data = {}
        save_data['settings'] = []
        save_data['settings'].append({
            'splitting_method': self.comboBoxSplittingMethod.currentIndex(),
            'splitting_scene_threshold': self.doubleSpinBoxFFmpegSceneThreshold.value(),
            'splitting_chunking_length': self.spinBoxChunking.value(),
            'splitting_chunking_reencode': self.checkBoxSplittingReencode.isChecked(),
            'splitting_chunking_codec': self.comboBoxSplittingReencode.currentIndex(),
            'worker_count': self.comboBoxWorkerCount.currentIndex(),
            'video_encoder': self.comboBoxEncoder.currentIndex(),
            'video_bit_depth': self.comboBoxBitDepth.currentIndex(),
            'video_color_fmt': self.comboBoxColorFormat.currentIndex(),
            'video_speed': self.horizontalSliderEncoderSpeed.value(),
            'video_passes': self.comboBoxPasses.currentIndex(),
            'video_advanced': self.checkBoxAdvancedSettings.isChecked(),
            'video_q': self.radioButtonCQ.isChecked(),
            'video_vbr': self.radioButtonVBR.isChecked(),
            'video_q_amount': self.horizontalSliderQ.value(),
            'video_vbr_amount': self.spinBoxVBR.value()
        })

        save_data['filters'] = []
        save_data['filters'].append({
            'filters_crop': self.groupBoxCrop.isChecked(),
            'filters_crop_top': self.spinBoxFilterCropTop.value(),
            'filters_crop_right': self.spinBoxFilterCropRight.value(),
            'filters_crop_bottom': self.spinBoxFilterCropBottom.value(),
            'filters_crop_left': self.spinBoxFilterCropLeft.value(),
            'filters_resize': self.groupBoxResize.isChecked(),
            'filters_resize_width': self.spinBoxFilterResizeWidth.value(),
            'filters_resize_height': self.spinBoxFilterResizeHeight.value(),
            'filters_rotate': self.groupBoxRotate.isChecked(),
            'filters_rotate_amount': self.comboBoxRotate.currentIndex(),
            'filters_deinterlace': self.groupBoxDeinterlace.isChecked(),
            'filters_deinterlace_type': self.comboBoxDeinterlace.currentIndex()
        })

        save_data['audio'] = []
        save_data['audio'].append({
            'track_one': self.groupBoxTrackOne.isChecked(),
            'track_two': self.groupBoxTrackTwo.isChecked(),
            'track_three': self.groupBoxTrackThree.isChecked(),
            'track_four': self.groupBoxTrackFour.isChecked(),
            'track_one_codec': self.comboBoxTrackOneCodec.currentIndex(),
            'track_two_codec': self.comboBoxTrackTwoCodec.currentIndex(),
            'track_three_codec': self.comboBoxTrackThreeCodec.currentIndex(),
            'track_four_codec': self.comboBoxTrackFourCodec.currentIndex(),
            'track_one_bitrate': self.spinBoxTrackOneBitrate.value(),
            'track_two_bitrate': self.spinBoxTrackTwoBitrate.value(),
            'track_three_bitrate': self.spinBoxTrackThreeBitrate.value(),
            'track_four_bitrate': self.spinBoxTrackFourBitrate.value(),
            'track_one_layout': self.comboBoxTrackOneLayout.currentIndex(),
            'track_two_layout': self.comboBoxTrackTwoLayout.currentIndex(),
            'track_three_layout': self.comboBoxTrackThreeLayout.currentIndex(),
            'track_four_layout': self.comboBoxTrackFourLayout.currentIndex(),
            'track_one_language': self.comboBoxTrackOneLanguage.currentIndex(),
            'track_two_language': self.comboBoxTrackTwoLanguage.currentIndex(),
            'track_three_language': self.comboBoxTrackThreeLanguage.currentIndex(),
            'track_four_language': self.comboBoxTrackFourLanguage.currentIndex()
        })

        if self.checkBoxAdvancedSettings.isChecked():
            self.groupBoxCustomSettings.setChecked(True)
            save_data['advanced_settings'] = []
            save_data['advanced_settings'].append({
                'command_line': self.textEditCustomSettings.toPlainText()
            })

        # Save JSON
        with open(os.path.join(self.current_dir, 'Presets', preset_name + ".json"), 'w') as outfile:
            json.dump(save_data, outfile)
        self.comboBoxPresets.clear()
        self.load_preset_startup()

    def save_preferences(self):
        save_data = {}
        save_data['preferences'] = []
        save_data['preferences'].append({
            'preset': self.comboBoxPresets.currentText(),
            'delete_temp_files': self.checkBoxDeleteTempFiles.isChecked(),
            'pixel_autodetect': self.checkBoxPixelAutoDetect.isChecked(),
            'logging': self.checkBoxLogging.isChecked()
        })
        # Save JSON
        with open(os.path.join(self.current_dir, "preferences.json"), 'w') as outfile:
            json.dump(save_data, outfile)

    def load_preferences(self):
        if os.path.isfile(os.path.join(self.current_dir, "preferences.json")):
            with open(os.path.join(self.current_dir, "preferences.json")) as json_file:
                data = json.load(json_file)
                for p in data['preferences']:
                    try:
                        self.checkBoxDeleteTempFiles.setChecked(p['delete_temp_files'])
                        self.checkBoxPixelAutoDetect.setChecked(p['pixel_autodetect'])
                        self.checkBoxLogging.setChecked(p['logging'])
                        index = self.comboBoxPresets.findText(p['preset'], Qt.MatchFixedString)
                        if index >= 0:
                            self.comboBoxPresets.setCurrentIndex(index)
                            self.load_preset()
                    except:
                        pass

    #  ════════════════════════════════════════ Filters ═══════════════════════════════════════

    def set_video_filters(self):
        crop = self.groupBoxCrop.isChecked() is True
        resize = self.groupBoxResize.isChecked() is True
        deinterlace = self.groupBoxDeinterlace.isChecked() is True
        rotate = self.groupBoxRotate.isChecked() is True
        counter = 0
        filter_command = ""

        if crop or resize or deinterlace or rotate:
            filter_command = " -vf "
            if crop:
                filter_command += self.video_crop()
                counter += 1
            if deinterlace:
                if counter != 0:
                    filter_command += ","
                filter_command += self.video_deinterlace()
                counter += 1
            if rotate:
                if counter != 0:
                    filter_command += ","
                filter_command += self.video_rotate()
                counter += 1
            if resize:
                if counter != 0:
                    filter_command += ","
                filter_command += self.video_resize() # !!! Has to be last, else ffmpeg logic fails
        self.filter_command = filter_command

    def video_crop(self):
        if self.groupBoxCrop.isChecked() is True:
            width_new = str(self.spinBoxFilterCropRight.value() + self.spinBoxFilterCropLeft.value())
            height_new = str(self.spinBoxFilterCropTop.value() + self.spinBoxFilterCropBottom.value())
            return "crop=iw-" + width_new + ":ih-" + height_new + ":" + str(self.spinBoxCropLeft.value()) + ":" + str(self.spinBoxCropTop.value())
        else:
            return None  # Needs to be set, else it will crop if in the same instance it was active

    def video_resize(self):
        if self.groupBoxResize.isChecked() is True:
            return "scale=" + str(self.spinBoxFilterResizeWidth.value()) + ":" + str(self.spinBoxFilterResizeHeight.value())
        else:
            return None

    def video_deinterlace(self):
        if self.groupBoxDeinterlace.isChecked() is True:
            return "yadif=" + self.comboBoxDeinterlace.currentText()
        else:
            return None

    def video_rotate(self):
        if self.groupBoxRotate.isChecked() is True:
            if self.comboBoxRotate.currentIndex() == 0:
                return "transpose=1"
            elif self.comboBoxRotate.currentIndex() == 1:
                return "transpose=2"
            elif self.comboBoxRotate.currentIndex() == 2:
                return "transpose=2,transpose=2"
            else:
                return None # unimplemented

    #  ═══════════════════════════════════════ Splitting ══════════════════════════════════════

    def splitting(self):
        # Create Temp Folder if not existant
        out_path = Path(os.path.join(self.tempDir, self.temp_dir_file_name, "Chunks"))
        out_path.mkdir(parents=True, exist_ok=True)
        out_path = Path(os.path.join(self.tempDir, self.temp_dir_file_name, "Progress"))
        out_path.mkdir(parents=True, exist_ok=True)
        # Select the correct splitting method
        current_index = self.comboBoxSplittingMethod.currentIndex()
        if current_index == 0:
            # FFmpeg Scene Detect
            self.labelStatus.setText("Status: Detecting Scenes")
            self.ffmpeg_scene_detect()
        elif current_index == 1:
            # Equal Chunking
            self.labelStatus.setText("Status: Splitting")
            self.ffmpeg_chunking()

    def ffmpeg_chunking(self):
        video_codec = [ ]
        # Set Splitting Parameters
        if self.checkBoxSplittingReencode.isChecked() is True:
            if self.comboBoxSplittingReencode.currentIndex() == 0:
                video_codec = ['libx264', '-crf', '0', '-preset', 'ultrafast']
            elif self.comboBoxSplittingReencode.currentIndex() == 1:
                video_codec = ['ffv1', '-level', '3', '-threads', '6', '-coder', '1', '-context', '1', '-g', '1', '-slicecrc', '0', '-slices', '4']
            elif self.comboBoxSplittingReencode.currentIndex() == 2:
                video_codec = ['utvideo']
        else:
            video_codec = ['copy']
        seg_time = str(self.spinBoxChunking.value())
        splitting_output = os.path.join(self.tempDir, self.temp_dir_file_name, "Chunks", "split%6d.mkv")

        # Create a QThread object
        self.thread_split = QThread()
        # Create a worker object
        self.worker_split = worker_splitting.WorkerSplitting()
        # Move worker to the thread
        self.worker_split.moveToThread(self.thread_split)
        # Connect signals and slots
        self.thread_split.started.connect(partial(self.worker_split.run, self.video_input, video_codec, seg_time, splitting_output))
        self.worker_split.finished.connect(self.thread_split.quit)
        self.worker_split.finished.connect(self.ffmpeg_splitting_finished)
        self.worker_split.finished.connect(self.worker_split.deleteLater)
        self.thread_split.finished.connect(self.thread_split.deleteLater)
        # Start the thread
        self.thread_split.start()

    def ffmpeg_splitting_finished(self):
        self.set_queue()
        self.get_source_framecount()

    def ffmpeg_scene_detect(self):
        threshold = str(self.doubleSpinBoxFFmpegSceneThreshold.value())
        splitting_output = os.path.join(self.tempDir, self.temp_dir_file_name, "splits.txt")
        # Create a QThread object
        self.thread_scene_detect = QThread()
        # Create a worker object
        self.worker_scene_detect = worker_scene.WorkerScene()
        # Move worker to the thread
        self.worker_scene_detect.moveToThread(self.thread_scene_detect)
        # Connect signals and slots
        self.thread_scene_detect.started.connect(partial(self.worker_scene_detect.run, self.video_input, threshold, splitting_output))
        self.worker_scene_detect.finished.connect(self.thread_scene_detect.quit)
        self.worker_scene_detect.finished.connect(self.ffmpeg_splitting_finished)
        self.worker_scene_detect.finished.connect(self.worker_scene_detect.deleteLater)
        self.thread_scene_detect.finished.connect(self.worker_scene_detect.deleteLater)
        # Start the thread
        self.thread_scene_detect.start()

    #  ═════════════════════════════════════════ Main ═════════════════════════════════════════

    def main_entry(self):
        # Check if input and output is set
        if self.video_input and self.video_output:
            if self.encode_started is False:
                self.progressBar.setValue(0)
                # Audio Encoding
                self.encode_started = True
                self.encode_audio()

        else:
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Warning)
            msg.setText("Please set Input and Output!")
            msg.setWindowTitle("Attention")
            msg.exec()

    #  ══════════════════════════════════ Command Generator ═══════════════════════════════════

    def set_pipe_color_fmt(self):
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
        self.pipe_color_fmt = fmt

    def set_encoder_settings(self):
        encoder = self.comboBoxEncoder.currentIndex()
        fmt = self.comboBoxColorFormat.currentIndex()
        passes = self.comboBoxPasses.currentIndex()
        settings = None
        if encoder == 0: # aomenc
            if passes == 0:
                self.encoder_passes = " --passes=1 "
            elif passes == 1:
                self.encoder_passes = " --passes=2 "
                self.encoder_pass_one = " --pass=1 "
                self.encoder_pass_two = " --pass=2 "

            self.encoder_output = " --output="
            self.encoder_output_stats = " --fpf="
            settings = "aomenc - --bit-depth=" + self.comboBoxBitDepth.currentText()

            if fmt == 0: # Color Format
                settings += " --i420"
            elif fmt == 1:
                settings += " --i422"
            elif fmt == 2:
                settings += " --i444"
            settings += " --cpu-used=" + str(self.horizontalSliderEncoderSpeed.value())

            if self.radioButtonCQ.isChecked() is True:
                settings += " --end-usage=q --cq-level=" + str(self.horizontalSliderQ.value())
            elif self.radioButtonVBR.isChecked() is True:
                settings += " --end-usage=vbr --target-bitrate=" + str(self.spinBoxVBR.value())

            if self.checkBoxAdvancedSettings.isChecked() is False:
                # Basic Settings
                settings += " --threads=4 --tile-columns=1 --tile-rows=2 "
            else:
                # Advanced Settings
                settings += " --threads=" + str(self.comboBoxAomencThreads.currentIndex())                  # Threads
                settings += " --tile-rows=" + str(self.comboBoxAomencTileRows.currentIndex())               # Tile Rows
                settings += " --tile-columns=" + str(self.comboBoxAomencTileCols.currentIndex())            # Tile Columns
                settings += " --kf-max-dist=" + str(self.spinBoxAomencGOP.value())                          # Max GOP
                settings += " --lag-in-frames=" + str(self.spinBoxAomencLagInFrames.value())                # Frame Buffer
                settings += " --tune=" + self.comboBoxAomencTune.currentText()                              # Tune
                settings += " --aq-mode=" + str(self.comboBoxAomencAQMode.currentIndex())                   # AQ Mode
                settings += " --color-primaries=" + self.comboBoxAomencColorPrimaries.currentText()         # Color Primaries
                settings += " --transfer-characteristics=" + self.comboBoxAomencColorTransfer.currentText() # Color Transfer
                settings += " --matrix-coefficients=" + self.comboBoxAomencColorMatrix.currentText()        # Color Matrix
                if self.checkBoxAomencDenoise.isChecked() is True:
                    settings += " --denoise-noise-level=" + str(self.spinBoxAomencDenoise.value())          # Denoise Noise Level
        elif encoder == 1: # rav1e
            self.encoder_output = " --output "
            self.encoder_passes = " " # rav1e still does not support 2pass encoding
            settings = "rav1e - --speed " + str(self.horizontalSliderEncoderSpeed.value())
            if self.radioButtonCQ.isChecked() is True:
                settings += " --quantizer " + str(self.horizontalSliderQ.value())
            elif self.radioButtonVBR.isChecked() is True:
                settings += " --bitrate " + str(self.spinBoxVBR.value())

            if self.checkBoxAdvancedSettings.isChecked() is False:
                # Basic Settings
                settings += " --threads 4 --tile-cols 1 --tile-rows 2"
            else:
                # Advanced Settings
                settings += " --threads " + str(self.comboBoxRav1eThreads.currentIndex())                   # Threads
                settings += " --tile-rows " + str(self.comboBoxRav1eTileRows.currentIndex())                # Tile Rows
                settings += " --tile-cols " + str(self.comboBoxRav1eTileCols.currentIndex())                # Tile Columns
                settings += " --keyint " + str(self.spinBoxRav1eGOP.value())                                # Max GOP
                settings += " --range " + self.comboBoxRav1eRange.currentText()                             # Color Range
                settings += " --primaries " + self.comboBoxRav1eColorPrimaries.currentText()                # Color Primaries
                settings += " --transfer " + self.comboBoxRav1eColorTransfer.currentText()                  # Color Transfer
                settings += " --matrix " + self.comboBoxRav1eColorMatrix.currentText()                      # Color Matrix
                settings += " --tune " + self.comboBoxRav1eTune.currentText()                               # Tune
                if self.checkBoxRav1eContentLight.isChecked() is True:
                    settings += " --content-light " + str(self.spinBoxRav1eCll.value())                     # Content Light Cll
                    settings += "," + str(self.spinBoxRav1eFall.value())                                    # Content Light Fall
                if self.groupBoxRav1eMastering.isChecked() is True:
                    settings += " --mastering-display G(" + str(self.spinBoxRav1eMasteringGx.value()) + "," # Mastering Gx
                    settings += str(self.spinBoxRav1eMasteringGy.value()) + ")B("                           # Mastering Gy
                    settings += str(self.spinBoxRav1eMasteringBx.value()) + ","                             # Mastering Bx
                    settings += str(self.spinBoxRav1eMasteringBy.value()) + ")R("                           # Mastering By
                    settings += str(self.spinBoxRav1eMasteringRx.value()) + ","                             # Mastering Rx
                    settings += str(self.spinBoxRav1eMasteringRy.value()) + ")WP("                          # Mastering Ry
                    settings += str(self.spinBoxRav1eMasteringWPx.value()) + ","                            # Mastering WPx
                    settings += str(self.spinBoxRav1eMasteringWPy.value()) + ")L("                          # Mastering WPy
                    settings += str(self.spinBoxRav1eMasteringLx.value()) + ","                             # Mastering Lx
                    settings += str(self.spinBoxRav1eMasteringLy.value()) + ")"                             # Mastering Ly
        elif encoder == 2: # svt-av1
            if passes == 0:
                self.encoder_passes = " --passes 1 "
            elif passes == 1:
                self.encoder_passes = " --irefresh-type 2 --passes 2 "
                self.encoder_pass_one = " --pass 1 "
                self.encoder_pass_two = " --pass 2 "
            self.encoder_output = " -b "
            settings = "SvtAv1EncApp -i stdin --preset " + str(self.horizontalSliderEncoderSpeed.value())
            if self.radioButtonCQ.isChecked() is True:
                settings += " --rc 0 -q " + str(self.horizontalSliderQ.value())
            elif self.radioButtonVBR.isChecked() is True:
                settings += " --rc 1 --tbr " + str(self.spinBoxVBR.value())
            if self.checkBoxRav1eContentLight.isChecked() is False:
                settings += " --tile-columns " + str(self.comboBoxSvtTileCols.currentIndex())
                settings += " --tile-rows " + str(self.comboBoxSvtTileRows.currentIndex())
                settings += " --keyint " + str(self.spinBoxSvtGOP.value())
                settings += " --adaptive-quantization " + str(self.comboBoxSvtAQ.currentIndex())
        self.encoder_settings = settings

    def set_queue(self):
        # Clear Queue
        self.video_queue_first_pass = []
        self.video_queue_second_pass = []

        self.set_video_filters()
        self.set_pipe_color_fmt()

        if self.groupBoxCustomSettings.isChecked():
            self.encoder_settings = self.textEditCustomSettings.toPlainText()
        else:
            self.set_encoder_settings()

        passes = self.comboBoxPasses.currentIndex()
        current_index = self.comboBoxSplittingMethod.currentIndex()
        encoder = self.comboBoxEncoder.currentIndex()

        if current_index == 0:
            # FFmpeg Scene Detect
            with open(os.path.join(self.tempDir, self.temp_dir_file_name, "splits.txt")) as file_splits:
                counter = 0
                for seek_point in file_splits:
                    out_file_name = str(counter).zfill(6)
                    temp_input_file = '\u0022' + self.video_input + '\u0022'
                    temp_output_file = '\u0022' + os.path.join(self.tempDir, self.temp_dir_file_name, "Chunks", "split" + out_file_name + ".ivf") + '\u0022'

                    if passes == 0:
                        temp_progress = " -progress " + '\u0022' + os.path.join(self.tempDir, self.temp_dir_file_name, "Progress", "split" + out_file_name + ".log") + '\u0022'
                        if encoder == 2: # svt-av1 specific
                            self.video_queue_first_pass.append("ffmpeg -loglevel 0 " + temp_progress + " -i " + temp_input_file + " " + seek_point.rstrip() + " -pix_fmt " + self.pipe_color_fmt + " " + self.filter_command + " -color_range 0 -vsync 0 -nostdin -f yuv4mpegpipe - | " + self.encoder_settings + self.encoder_passes + self.encoder_output + temp_output_file)
                        else:
                            self.video_queue_first_pass.append("ffmpeg -loglevel 0 " + temp_progress + " -i " + temp_input_file + " " + seek_point.rstrip() + " -pix_fmt " + self.pipe_color_fmt + " " + self.filter_command + " -color_range 0 -vsync 0 -f yuv4mpegpipe - | " + self.encoder_settings + self.encoder_passes + self.encoder_output + temp_output_file)
                    elif passes == 1:
                        temp_output_file_log = '\u0022' + os.path.join(self.tempDir, self.temp_dir_file_name, "Chunks", "split" + out_file_name + ".stats") + '\u0022'
                        temp_progress_first = " -progress " + '\u0022' + os.path.join(self.tempDir, self.temp_dir_file_name, "Progress", "1st_split" + out_file_name + ".log") + '\u0022'
                        temp_progress_second = " -progress " + '\u0022' + os.path.join(self.tempDir, self.temp_dir_file_name, "Progress", "2nd_split" + out_file_name + ".log") + '\u0022'
                        if encoder == 2: # svt-av1 specific
                            self.video_queue_first_pass.append("ffmpeg -loglevel 0 " + temp_progress_first + " -i " + temp_input_file + " " + seek_point.rstrip() + " -pix_fmt " + self.pipe_color_fmt + " " + self.filter_command + " -color_range 0 -vsync 0 -nostdin -f yuv4mpegpipe - | " + self.encoder_settings + self.encoder_passes + self.encoder_pass_one + self.encoder_output + self.null_path + self.encoder_output_stats + temp_output_file_log)
                            self.video_queue_second_pass.append("ffmpeg -loglevel 0 " + temp_progress_second + " -i " + temp_input_file + " " + seek_point.rstrip() + " -pix_fmt " + self.pipe_color_fmt + " " + self.filter_command + " -color_range 0 -vsync 0 -nostdin -f yuv4mpegpipe - | " + self.encoder_settings + self.encoder_passes + self.encoder_pass_two + self.encoder_output + temp_output_file + self.encoder_output_stats + temp_output_file_log)
                        else:
                            self.video_queue_first_pass.append("ffmpeg -loglevel 0 " + temp_progress_first + " -i " + temp_input_file + " " + seek_point.rstrip() + " -pix_fmt " + self.pipe_color_fmt + " " + self.filter_command + " -color_range 0 -vsync 0 -f yuv4mpegpipe - | " + self.encoder_settings + self.encoder_passes + self.encoder_pass_one + self.encoder_output + self.null_path + self.encoder_output_stats + temp_output_file_log)
                            self.video_queue_second_pass.append("ffmpeg -loglevel 0 " + temp_progress_second + " -i " + temp_input_file + " " + seek_point.rstrip() + " -pix_fmt " + self.pipe_color_fmt + " " + self.filter_command + " -color_range 0 -vsync 0 -f yuv4mpegpipe - | " + self.encoder_settings + self.encoder_passes + self.encoder_pass_two + self.encoder_output + temp_output_file + self.encoder_outputStats + temp_output_file_log)
                    counter += 1
        elif current_index == 1:
            # Equal Chunking
            files = os.listdir(os.path.join(self.tempDir, self.temp_dir_file_name, "Chunks"))
            # Iterate over all mkv files
            for file in files:
                if file.endswith(".mkv"):
                    temp_input_file = '\u0022' + os.path.join(self.tempDir, self.temp_dir_file_name, "Chunks", file) + '\u0022'
                    temp_output_file = '\u0022' + os.path.join(self.tempDir, self.temp_dir_file_name, "Chunks", os.path.splitext(os.path.basename(str(file)))[0] + ".ivf") + '\u0022'
                    if passes == 0:
                        temp_progress = " -progress " + '\u0022' + os.path.join(self.tempDir, self.temp_dir_file_name, "Progress", os.path.splitext(os.path.basename(str(file)))[0] + ".log") + '\u0022'
                        if encoder == 2: # svt-av1 specific
                            self.video_queue_first_pass.append("ffmpeg -loglevel 0 " + temp_progress + " -i " + temp_input_file + " -pix_fmt " + self.pipe_color_fmt + " -color_range 0 -vsync 0 -nostdin -f yuv4mpegpipe - | " + self.encoder_settings + self.encoder_passes + self.encoder_output + temp_output_file)
                        else:
                            self.video_queue_first_pass.append("ffmpeg -loglevel 0 " + temp_progress + " -i " + temp_input_file + " -pix_fmt " + self.pipe_color_fmt + " -color_range 0 -vsync 0 -f yuv4mpegpipe - | " + self.encoder_settings + self.encoder_passes + self.encoder_output + temp_output_file)
                    elif passes == 1:
                        temp_output_file_log = '\u0022' + os.path.join(self.tempDir, self.temp_dir_file_name, "Chunks", os.path.splitext(os.path.basename(str(file)))[0] + ".stats") + '\u0022'
                        temp_progress_first = " -progress " + '\u0022' + os.path.join(self.tempDir, self.temp_dir_file_name, "Progress", "1st_split" + os.path.splitext(os.path.basename(str(file)))[0] + ".log") + '\u0022'
                        temp_progress_second = " -progress " + '\u0022' + os.path.join(self.tempDir, self.temp_dir_file_name, "Progress", "2nd_split" + os.path.splitext(os.path.basename(str(file)))[0] + ".log") + '\u0022'
                        if encoder == 2: # svt-av1 specific
                            self.video_queue_first_pass.append("ffmpeg -loglevel 0 " + temp_progress_first + " -i " + temp_input_file + " -pix_fmt " + self.pipe_color_fmt + " -color_range 0 -vsync 0 -nostdin -f yuv4mpegpipe - | " + self.encoder_settings + self.encoder_passes + self.encoder_pass_one + self.encoder_output + self.null_path + self.encoder_output_stats + temp_output_file_log)
                            self.video_queue_second_pass.append("ffmpeg -loglevel 0 " + temp_progress_second + " -i " + temp_input_file + " -pix_fmt " + self.pipe_color_fmt + " -color_range 0 -vsync 0 -nostdin -f yuv4mpegpipe - | " + self.encoder_settings + self.encoder_passes + self.encoder_pass_two + self.encoder_output + temp_output_file + self.encoder_output_stats + temp_output_file_log)
                        else:
                            self.video_queue_first_pass.append("ffmpeg -loglevel 0 " + temp_progress_first + " -i " + temp_input_file + " -pix_fmt " + self.pipe_color_fmt + " -color_range 0 -vsync 0 -f yuv4mpegpipe - | " + self.encoder_settings + self.encoder_passes + self.encoder_pass_one + self.encoder_output + self.null_path + self.encoder_output_stats + temp_output_file_log)
                            self.video_queue_second_pass.append("ffmpeg -loglevel 0 " + temp_progress_second + " -i " + temp_input_file + " -pix_fmt " + self.pipe_color_fmt + " -color_range 0 -vsync 0 -f yuv4mpegpipe - | " + self.encoder_settings + self.encoder_passes + self.encoder_pass_two + self.encoder_output + temp_output_file + self.encoder_output_stats + temp_output_file_log)

    #  ═══════════════════════════════════════ Encoding ═══════════════════════════════════════

    def pause_ffmpeg(self):
        tasklist=['ffmpeg']
        out=[]
        for proc in psutil.process_iter():
            if any(task in proc.name() for task in tasklist):
                out.append(proc.pid)
        for pid in out:
            p = psutil.Process(pid)
            p.suspend()

    def resume_ffmpeg(self):
        tasklist=['ffmpeg']
        out=[]
        for proc in psutil.process_iter():
            if any(task in proc.name() for task in tasklist):
                out.append(proc.pid)
        for pid in out:
            p = psutil.Process(pid)
            p.resume()

    def set_framecount(self, count):
        frame_count = count
        if self.comboBoxPasses.currentIndex() == 1:
            frame_count = frame_count * 2
        if self.groupBoxDeinterlace.isChecked() and self.comboBoxDeinterlace.currentIndex() == 1:
            frame_count = frame_count * 2
        self.progressBar.setMaximum(frame_count)
        self.labelStatus.setText("Status: 0 / " + str(frame_count) + " Frames")
        self.save_to_log("Framecount : " + str(frame_count))
        self.total_frame_count = frame_count

    def get_source_framecount(self):
        # Create a QThread object
        self.frame_thread = QThread()
        # Create a worker object
        self.frame_worker = worker_framecount.WorkerFramecount()
        # Move worker to the thread
        self.frame_worker.moveToThread(self.frame_thread)
        # Connect signals and slots
        self.frame_thread.started.connect(partial(self.frame_worker.run, self.video_input))
        self.frame_worker.finished.connect(self.frame_thread.quit)
        self.frame_worker.finished.connect(self.frame_worker.deleteLater)
        self.frame_worker.finished.connect(self.main_encode)
        self.frame_thread.finished.connect(self.frame_thread.deleteLater)
        self.frame_worker.framecount.connect(self.set_framecount)
        # Start the thread
        self.frame_thread.start()

    def calc_progress(self):
        log_path = os.path.join(self.tempDir, self.temp_dir_file_name, "Progress")
        mux_path = os.path.join(self.tempDir, self.temp_dir_file_name, "Chunks", "mux.txt")
        # Create a QThread object
        self.calc_thread = QThread()
        # Create a worker object
        self.calc_worker = worker_progress.WorkerProgress()
        # Move worker to the thread
        self.calc_worker.moveToThread(self.calc_thread)
        # Connect signals and slots
        self.calc_thread.started.connect(partial(self.calc_worker.run, log_path, mux_path))
        self.calc_worker.finished.connect(self.calc_thread.quit)
        self.calc_worker.finished.connect(self.calc_worker.deleteLater)
        self.calc_thread.finished.connect(self.calc_thread.deleteLater)
        self.calc_worker.progress.connect(self.report_progress)
        # Start the thread
        self.calc_thread.start()

    def main_encode(self):
        pool_size = self.comboBoxWorkerCount.currentIndex() + 1
        queue_one = self.video_queue_first_pass
        queue_two = self.video_queue_second_pass
        self.save_to_log("Pool Size: " + str(pool_size))
        self.save_to_log("Queue One: " + str(queue_one))
        self.save_to_log("Queue Two: " + str(queue_two))
        # Create a QThread object
        self.thread = QThread()
        # Create a worker object
        self.worker = worker.Worker()
        # Move worker to the thread
        self.worker.moveToThread(self.thread)
        # Connect signals and slots
        self.thread.started.connect(partial(self.worker.run, pool_size, queue_one, queue_two))
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker_finished)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        # Start the thread
        self.thread.start()
        self.calc_progress()

    def worker_finished(self):
        self.labelStatus.setText("Status: Muxing")
        self.main_muxing()
        self.labelStatus.setText("Status: Finished")

    #  ════════════════════════════════════════ Muxing ════════════════════════════════════════

    def main_muxing(self):
        # Creates the list file of all encoded chunks for ffmpeg concat
        files = os.listdir(os.path.join(self.tempDir, self.temp_dir_file_name, "Chunks"))
        fname = open(os.path.join(self.tempDir, self.temp_dir_file_name, "Chunks", "mux.txt"), "a")
        sorted_files = sorted(files)
        for file in sorted_files:
            if file.endswith(".ivf"):
                temp_input_file = '\u0027' + os.path.join(self.tempDir, self.temp_dir_file_name, "Chunks", file) + '\u0027'
                fname.write("file " + temp_input_file + "\n")
        fname.close()
        if self.audio_encoding:
            temp_video = os.path.join(self.tempDir, self.temp_dir_file_name, "temp.mkv")
            temp_audio = os.path.join(self.tempDir, self.temp_dir_file_name, "Audio", "audio.mkv")
            subprocess.call(['ffmpeg', '-y','-f', 'concat', '-safe', '0', '-i', os.path.join(self.tempDir, self.temp_dir_file_name, "Chunks", "mux.txt"), '-c', 'copy', temp_video])
            self.save_to_log("Mux: " + str(['ffmpeg', '-y','-f', 'concat', '-safe', '0', '-i', os.path.join(self.tempDir, self.temp_dir_file_name, "Chunks", "mux.txt"), '-c', 'copy', temp_video]))
            subprocess.call(['ffmpeg', '-y','-i', temp_video, '-i', temp_audio, '-c', 'copy', self.video_output])
            self.save_to_log("Mux: " + str(['ffmpeg', '-y','-i', temp_video, '-i', temp_audio, '-c', 'copy', self.video_output]))
        else:
            subprocess.call(['ffmpeg', '-y','-f', 'concat', '-safe', '0', '-i', os.path.join(self.tempDir, self.temp_dir_file_name, "Chunks", "mux.txt"), '-c', 'copy', self.video_output])
            self.save_to_log("Mux: " + str(['ffmpeg', '-y','-f', 'concat', '-safe', '0', '-i', os.path.join(self.tempDir, self.temp_dir_file_name, "Chunks", "mux.txt"), '-c', 'copy', self.video_output]))
        self.delete_temp_files()
        self.encode_started = False

    def delete_temp_files(self):
        if self.checkBoxDeleteTempFiles.isChecked():
            if os.path.isfile(self.video_output):
                if os.stat(self.video_output).st_size >= 50000:
                    #print(os.path.join(self.tempDir, self.temp_dir_file_name))
                    shutil.rmtree(os.path.join(self.tempDir, self.temp_dir_file_name))
                else:
                    msg = QMessageBox()
                    msg.setIcon(QMessageBox.Warning)
                    msg.setText("Output File found, but there could be a muxing issue.")
                    msg.setWindowTitle("Attention")
                    msg.exec()
            else:
                msg = QMessageBox()
                msg.setIcon(QMessageBox.Critical)
                msg.setText("Output File not found!")
                msg.setWindowTitle("Attention")
                msg.exec()


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = neav1e()
    app.exec_()
