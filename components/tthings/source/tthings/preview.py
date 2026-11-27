"""Animated catalogue previews with a deterministic terminal-safe dissolve."""
from .effects import Frame, Scene


class GalleryPreview:
    """Keep the selected preview live and dissolve between selected scenes."""
    TRANSITION=.32

    def __init__(self,scene_factory=Scene):
        self.scene_factory=scene_factory
        self.scene_id=None
        self.scene=None
        self.started=0.
        self.transition_started=None
        self.outgoing=None
        self.last_frame=None

    def select(self,scene_id,now):
        if scene_id==self.scene_id:return
        self.outgoing=self.last_frame
        self.scene_id=scene_id
        self.scene=self.scene_factory(scene_id)
        self.started=now
        self.transition_started=now if self.outgoing is not None else None

    @staticmethod
    def _fit(frame,width,height):
        fitted=Frame(width,height)
        if frame is None:return fitted
        for y,row in enumerate(frame.cells[:height]):
            fitted.cells[y][:min(width,len(row))]=row[:width]
        return fitted

    def render(self,width,height,now,palette=0):
        width=max(1,width);height=max(1,height)
        if self.scene is None:return Frame(width,height)
        current=self.scene.render(width,height,max(0.,now-self.started),palette)
        if self.outgoing is None or self.transition_started is None:
            result=current
        else:
            progress=max(0.,min(1.,(now-self.transition_started)/self.TRANSITION))
            old=self._fit(self.outgoing,width,height)
            result=Frame(width,height)
            for y,row in enumerate(current.cells):
                for x,cell in enumerate(row):
                    threshold=((x*13+y*7)%32)/32
                    result.cells[y][x]=cell if threshold<progress else old.cells[y][x]
            if progress>=1.:
                self.outgoing=None
                self.transition_started=None
        self.last_frame=self._fit(result,width,height)
        return result