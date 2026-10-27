from Screens.Screen import Screen
from Components.ActionMap import ActionMap
from Components.Pixmap import Pixmap
from Components.Label import Label
from enigma import getDesktop, ePicLoad
import os
import glob

from ..utils.logging_config import get_logger

logger = get_logger(__name__)

class ImageViewer(Screen):
    """Simple image viewer with slideshow"""
    
    def __init__(self, session, image_path=None, image_list=None, directory=None):
        Screen.__init__(self, session)
        
        # Get screen dimensions
        w, h = getDesktop(0).size().width(), getDesktop(0).size().height()
        
        self.image_path = image_path
        self.directory = directory
        
        # Get image list
        self.image_list = self.get_image_list(image_path, image_list, directory)
        self.current_index = 0
        
        # Find current index
        if self.image_path and self.image_list:
            try:
                self.current_index = self.image_list.index(self.image_path)
            except ValueError:
                self.current_index = 0
        
        # Create skin
        self.skin = """
        <screen name="ImageViewer" position="0,0" size="%d,%d" backgroundColor="#000000" flags="wfNoBorder">
            <widget name="image" position="0,0" size="%d,%d" alphatest="on" />
            <eLabel position="0,%d" size="%d,80" backgroundColor="#1a1a1a" zPosition="-1" />
            <widget name="info" position="10,%d" size="%d,40" font="Regular;20" halign="left" transparent="1" foregroundColor="#ffffff" />
            <widget name="help" position="10,%d" size="%d,30" font="Regular;18" halign="left" transparent="1" foregroundColor="#ffff00" />
        </screen>""" % (w, h, w, h-80, h-80, w, h-75, w-20, h-40, w-20)
        
        # Create widgets
        self["image"] = Pixmap()
        self["info"] = Label("")
        
        # Set help text based on number of images
        if len(self.image_list) > 1:
            self["help"] = Label("LEFT:Prev  RIGHT:Next  EXIT:Close")
        else:
            self["help"] = Label("EXIT:Close")
        
        # Initialize ePicLoad
        self.picload = ePicLoad()
        self.picload.PictureData.get().append(self.update_image)
        
        # Setup actions
        self["actions"] = ActionMap(["DirectionActions", "OkCancelActions"], 
        {
            "cancel": self.key_exit,
            "ok": self.key_exit,
            "left": self.prev_image,
            "right": self.next_image,
            "up": self.key_exit,
            "down": self.key_exit,
        }, -1)
        
        # Load image
        self.onLayoutFinish.append(self.load_image)
    
    def __del__(self):
        """Clean up the callback to prevent crashes on close"""
        try:
            if self.update_image in self.picload.PictureData.get():
                self.picload.PictureData.get().remove(self.update_image)
        except Exception as e:
            logger.debug("Error in ImageViewer cleanup: %s" % str(e))
            
    def get_image_list(self, image_path, image_list, directory):
        """Get list of images to display"""
        if image_list and len(image_list) > 0:
            return image_list
        
        # If directory is provided, get all images from that directory
        if directory and os.path.isdir(directory):
            image_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.gif']
            all_files = []
            for ext in image_extensions:
                all_files.extend(glob.glob(os.path.join(directory, f"*{ext}")))
                all_files.extend(glob.glob(os.path.join(directory, f"*{ext.upper()}")))
            return sorted(all_files)
        
        # If only single image path is provided
        if image_path and os.path.isfile(image_path):
            # Get all images in the same directory
            dir_path = os.path.dirname(image_path)
            image_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.gif']
            all_files = []
            for ext in image_extensions:
                all_files.extend(glob.glob(os.path.join(dir_path, f"*{ext}")))
                all_files.extend(glob.glob(os.path.join(dir_path, f"*{ext.upper()}")))
            return sorted(all_files)
        
        return []
    
    def load_image(self):
        """Load the image"""
        if not self.image_path or not self.image_list:
            self["info"].setText("No image selected!")
            return
        
        try:
            if not os.path.isfile(self.image_path):
                self["info"].setText("Image not found!")
                return
            
            file_name = os.path.basename(self.image_path)
            
            # Show image counter if we have a list
            if len(self.image_list) > 1:
                info_text = "[%d/%d] %s" % (self.current_index + 1, len(self.image_list), file_name)
            else:
                info_text = file_name
            
            self["info"].setText(info_text)
            
            # Get screen dimensions
            w, h = getDesktop(0).size().width(), getDesktop(0).size().height()
            
            # Load image
            self.picload.setPara([w, h-80, 1, 1, 0, 0, "#000000"])
            self.picload.startDecode(self.image_path)
            
        except Exception as e:
            logger.error("Error loading image: %s" % str(e))
            self["info"].setText("Error: %s" % str(e))
    
    def update_image(self, picInfo=None):
        """Update the image display"""
        try:
            ptr = self.picload.getData()
            if ptr:
                self["image"].instance.setPixmap(ptr)
                self["image"].show()
        except Exception as e:
            logger.error("Error updating image: %s" % str(e))
    
    def prev_image(self):
        """Load previous image in slideshow"""
        if len(self.image_list) <= 1:
            self["help"].setText("Only one image in folder")
            return
        
        # Calculate previous index
        self.current_index -= 1
        if self.current_index < 0:
            self.current_index = len(self.image_list) - 1
        
        self.image_path = self.image_list[self.current_index]
        self.load_image()
    
    def next_image(self):
        """Load next image in slideshow"""
        if len(self.image_list) <= 1:
            self["help"].setText("Only one image in folder")
            return
        
        # Calculate next index
        self.current_index += 1
        if self.current_index >= len(self.image_list):
            self.current_index = 0
        
        self.image_path = self.image_list[self.current_index]
        self.load_image()
    
    def key_exit(self):
        """Exit viewer"""
        self.close()