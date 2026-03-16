# import numpy as np
# import cv2
# import onnxruntime as ort


# class Detection:
#     def __init__(self, bbox_xyxy, conf: float, class_id: int, class_name: str):
#         self.bbox_xyxy = bbox_xyxy  # (x1, y1, x2, y2)
#         self.conf = conf
#         self.class_id = class_id
#         self.class_name = class_name

#     def center(self):
#         x1, y1, x2, y2 = self.bbox_xyxy
#         return (0.5 * (x1 + x2), 0.5 * (y1 + y2))

#     def area(self):
#         x1, y1, x2, y2 = self.bbox_xyxy
#         return max(0, x2 - x1) * max(0, y2 - y1)


# def iou_xyxy(a, b):
#     ax1, ay1, ax2, ay2 = a
#     bx1, by1, bx2, by2 = b

#     ix1 = max(ax1, bx1)
#     iy1 = max(ay1, by1)
#     ix2 = min(ax2, bx2)
#     iy2 = min(ay2, by2)

#     iw = max(0, ix2 - ix1)
#     ih = max(0, iy2 - iy1)
#     inter = iw * ih

#     area_a = max(0, ax2 - ax1) * max(0, ay2 - ay1)
#     area_b = max(0, bx2 - bx1) * max(0, by2 - by1)

#     denom = area_a + area_b - inter + 1e-9
#     return inter / denom


# def nms(dets, iou_thres):
#     dets = sorted(dets, key=lambda d: d.conf, reverse=True)
#     keep = []

#     for d in dets:
#         ok = True
#         for k in keep:
#             if iou_xyxy(d.bbox_xyxy, k.bbox_xyxy) > iou_thres:
#                 ok = False
#                 break
#         if ok:
#             keep.append(d)

#     return keep


# class YOLODetector:
#     """
#     ONNX YOLO detector + motion-based post-filter.

#     Mantık:
#     - YOLO her zaman orijinal görüntüde çalışır.
#     - Motion mask ayrı hesaplanır.
#     - Eğer detection kutusu içinde yeterli motion yoksa detection reddedilir.

#     Not:
#     - Eğer ONNX output shape farklıysa _postprocess_fast içinde küçük düzeltme gerekebilir.
#     """

#     def __init__(
#         self,
#         onnx_path: str,
#         input_size: int,
#         conf_thres: float,
#         iou_thres: float,
#         class_name: str,
#         providers=None
#     ):
#         self.onnx_path = onnx_path
#         self.input_size = 320  # istersen input_size yapabilirsin
#         self.conf_thres = conf_thres
#         self.iou_thres = iou_thres
#         self.class_name = class_name

#         cpu_providers = ['CPUExecutionProvider']

#         options = ort.SessionOptions()
#         options.intra_op_num_threads = 4
#         options.inter_op_num_threads = 4
#         options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
#         options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

#         self.sess = ort.InferenceSession(
#             onnx_path,
#             sess_options=options,
#             providers=cpu_providers
#         )

#         self.in_name = self.sess.get_inputs()[0].name
#         self.out_names = [o.name for o in self.sess.get_outputs()]
#         self.input_shape = self.sess.get_inputs()[0].shape
#         self.last_letterbox_params = None

#         # -----------------------------
#         # Motion filter ayarları
#         # -----------------------------
#         self.use_motion_filter = True
#         self.motion_threshold = 25
#         self.motion_min_area = 20
#         self.prev_gray = None
#         self.last_motion_mask = None

#         # Detection kutusu içinde minimum hareket oranı
#         self.min_motion_ratio_in_box = 0.02 #0.03 dü
#         self.min_box_area_for_motion_check = 25

#     def _letterbox_fast(self, img):
#         h, w = img.shape[:2]
#         s = self.input_size

#         scale = s / max(h, w)
#         nw = int(w * scale)
#         nh = int(h * scale)

#         resized = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)

#         canvas = np.full((s, s, 3), 114, dtype=np.uint8)
#         pad_x = (s - nw) // 2
#         pad_y = (s - nh) // 2
#         canvas[pad_y:pad_y + nh, pad_x:pad_x + nw] = resized

#         return canvas, scale, pad_x, pad_y

#     def _estimate_global_motion(self, prev_gray, curr_gray):
#         """
#         Önceki ve mevcut frame arasında global hareketi affine olarak tahmin eder.
#         Başarısız olursa identity döner.
#         """
#         pts_prev = cv2.goodFeaturesToTrack(
#             prev_gray,
#             maxCorners=300,
#             qualityLevel=0.01,
#             minDistance=7,
#             blockSize=7
#         )

#         if pts_prev is None or len(pts_prev) < 8:
#             return np.array([[1, 0, 0], [0, 1, 0]], dtype=np.float32)

#         pts_curr, status, _ = cv2.calcOpticalFlowPyrLK(
#             prev_gray,
#             curr_gray,
#             pts_prev,
#             None
#         )

#         if pts_curr is None or status is None:
#             return np.array([[1, 0, 0], [0, 1, 0]], dtype=np.float32)

#         good_prev = pts_prev[status.flatten() == 1]
#         good_curr = pts_curr[status.flatten() == 1]

#         if len(good_prev) < 8 or len(good_curr) < 8:
#             return np.array([[1, 0, 0], [0, 1, 0]], dtype=np.float32)

#         M, _ = cv2.estimateAffinePartial2D(
#             good_prev,
#             good_curr,
#             method=cv2.RANSAC,
#             ransacReprojThreshold=3.0
#         )

#         if M is None:
#             M = np.array([[1, 0, 0], [0, 1, 0]], dtype=np.float32)

#         return M.astype(np.float32)

#     def _create_motion_mask(self, prev_gray, curr_gray):
#         """
#         Kamera hareketini bastırıp residual motion mask üretir.
#         """
#         h, w = curr_gray.shape[:2]

#         M = self._estimate_global_motion(prev_gray, curr_gray)

#         aligned_prev = cv2.warpAffine(
#             prev_gray,
#             M,
#             (w, h),
#             flags=cv2.INTER_LINEAR,
#             borderMode=cv2.BORDER_REPLICATE
#         )

#         diff = cv2.absdiff(curr_gray, aligned_prev)
#         diff = cv2.GaussianBlur(diff, (5, 5), 0)

#         _, motion_mask = cv2.threshold(
#             diff,
#             self.motion_threshold,
#             255,
#             cv2.THRESH_BINARY
#         )

#         kernel_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
#         kernel_dilate = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))

#         motion_mask = cv2.morphologyEx(motion_mask, cv2.MORPH_OPEN, kernel_open)
#         motion_mask = cv2.dilate(motion_mask, kernel_dilate, iterations=1)

#         num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(motion_mask, 8)
#         cleaned = np.zeros_like(motion_mask)

#         for i in range(1, num_labels):
#             area = stats[i, cv2.CC_STAT_AREA]
#             if area >= self.motion_min_area:
#                 cleaned[labels == i] = 255

#         return cleaned

#     def _update_motion_mask(self, bgr):
#         """
#         Motion mask üretir ve self.last_motion_mask içine kaydeder.
#         YOLO input'unu değiştirmez.
#         """
#         curr_gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

#         if self.prev_gray is None:
#             self.prev_gray = curr_gray.copy()
#             self.last_motion_mask = np.zeros_like(curr_gray, dtype=np.uint8)
#             return

#         motion_mask = self._create_motion_mask(self.prev_gray, curr_gray)
#         self.prev_gray = curr_gray.copy()
#         self.last_motion_mask = motion_mask

#     def _motion_ratio_in_box(self, bbox_xyxy, motion_mask):
#         """
#         Detection kutusu içindeki hareketli piksel oranını hesaplar.
#         """
#         if motion_mask is None:
#             return 1.0

#         H, W = motion_mask.shape[:2]
#         x1, y1, x2, y2 = bbox_xyxy

#         x1 = int(max(0, min(W - 1, x1)))
#         y1 = int(max(0, min(H - 1, y1)))
#         x2 = int(max(0, min(W, x2)))
#         y2 = int(max(0, min(H, y2)))

#         if x2 <= x1 or y2 <= y1:
#             return 0.0

#         roi = motion_mask[y1:y2, x1:x2]
#         if roi.size == 0:
#             return 0.0

#         box_area = roi.shape[0] * roi.shape[1]
#         if box_area < self.min_box_area_for_motion_check:
#             return 1.0

#         moving_pixels = np.count_nonzero(roi > 0)
#         return moving_pixels / float(box_area)

#     def _filter_detections_by_motion(self, dets, motion_mask):
#         """
#         Detection'ları kutu içindeki motion oranına göre filtreler.
#         """
#         if motion_mask is None or len(dets) == 0:
#             return dets

#         kept = []
#         for d in dets:
#             ratio = self._motion_ratio_in_box(d.bbox_xyxy, motion_mask)
#             if ratio >= self.min_motion_ratio_in_box:
#                 kept.append(d)

#         return kept

#     def detect(self, bgr, last_track=None):
#         """
#         last_track:
#             Eğer bir önceki karede drone bulunduysa, onun koordinatlarını gönderir.
#         """
#         if self.use_motion_filter:
#             self._update_motion_mask(bgr)

#         roi_offset = (0, 0)
#         inference_img = bgr
#         actual_shape = bgr.shape
#         motion_mask_for_filter = self.last_motion_mask

#         # --- ROI SEÇİMİ ---
#         if last_track is not None:
#             x1_t, y1_t, x2_t, y2_t = last_track.bbox_xyxy
#             cx = (x1_t + x2_t) / 2.0
#             cy = (y1_t + y2_t) / 2.0

#             roi_size = 320
#             H, W = bgr.shape[:2]

#             roi_w = min(roi_size, W)
#             roi_h = min(roi_size, H)

#             r_x1 = int(np.clip(cx - roi_w // 2, 0, max(0, W - roi_w)))
#             r_y1 = int(np.clip(cy - roi_h // 2, 0, max(0, H - roi_h)))

#             inference_img = bgr[r_y1:r_y1 + roi_h, r_x1:r_x1 + roi_w]
#             roi_offset = (r_x1, r_y1)
#             actual_shape = inference_img.shape

#             if motion_mask_for_filter is not None:
#                 motion_mask_for_filter = motion_mask_for_filter[
#                     r_y1:r_y1 + roi_h,
#                     r_x1:r_x1 + roi_w
#                 ]

#         # --- PRE-PROCESSING ---
#         inference_img = cv2.GaussianBlur(inference_img, (3, 3), 0)
#         img, scale, pad_x, pad_y = self._letterbox_fast(inference_img)

#         rgb = img[..., ::-1].transpose(2, 0, 1)
#         x = np.ascontiguousarray(rgb[None, ...], dtype=np.float32) / 255.0

#         # --- INFERENCE ---
#         outs = self.sess.run(self.out_names, {self.in_name: x})

#         # --- POST-PROCESSING ---
#         dets = self._postprocess_fast(outs, actual_shape, scale, pad_x, pad_y)

#         # Motion tabanlı filtre
#         if self.use_motion_filter:
#             dets = self._filter_detections_by_motion(dets, motion_mask_for_filter)

#         # ROI kullanıldıysa koordinatları orijinal tam resme geri taşı
#         if last_track is not None and len(dets) > 0:
#             translated = []
#             ox, oy = roi_offset

#             for d in dets:
#                 nx1, ny1, nx2, ny2 = d.bbox_xyxy
#                 translated_bbox = (nx1 + ox, ny1 + oy, nx2 + ox, ny2 + oy)
#                 translated.append(
#                     Detection(translated_bbox, d.conf, d.class_id, d.class_name)
#                 )
#             dets = translated

#         return dets

#     def _postprocess_fast(self, outs, img_shape, scale, pad_x, pad_y):
#         y = outs[0][0]

#         # Bazı exportlarda shape [5, N] gelebiliyor
#         if len(y.shape) == 2 and y.shape[0] == 5:
#             y = y.T

#         scores = y[:, 4]
#         mask = scores >= self.conf_thres

#         if not np.any(mask):
#             return []

#         filtered = y[mask]
#         confidences = filtered[:, 4]

#         cxs = filtered[:, 0]
#         cys = filtered[:, 1]
#         wws = filtered[:, 2]
#         hhs = filtered[:, 3]

#         x1 = (cxs - wws / 2.0 - pad_x) / scale
#         y1 = (cys - hhs / 2.0 - pad_y) / scale
#         x2 = (cxs + wws / 2.0 - pad_x) / scale
#         y2 = (cys + hhs / 2.0 - pad_y) / scale

#         H, W = img_shape[:2]
#         x1 = np.clip(x1, 0, W - 1)
#         y1 = np.clip(y1, 0, H - 1)
#         x2 = np.clip(x2, 0, W - 1)
#         y2 = np.clip(y2, 0, H - 1)

#         all_dets = []
#         for i in range(len(filtered)):
#             bbox = (float(x1[i]), float(y1[i]), float(x2[i]), float(y2[i]))
#             all_dets.append(
#                 Detection(bbox, float(confidences[i]), 0, self.class_name)
#             )

#         # İstersen burada gerçek NMS de kullanabilirsin:
#         # all_dets = nms(all_dets, self.iou_thres)

#         # Şu an en hızlı yaklaşım: sadece en yüksek confident olanı döndür
#         if all_dets:
#             return [max(all_dets, key=lambda d: d.conf)]

#         return []

import numpy as np
import cv2
import onnxruntime as ort


class Detection:
    def __init__(self, bbox_xyxy, conf: float, class_id: int, class_name: str):
        self.bbox_xyxy = bbox_xyxy  # (x1, y1, x2, y2)
        self.conf = conf
        self.class_id = class_id
        self.class_name = class_name

    def center(self):
        x1, y1, x2, y2 = self.bbox_xyxy
        return (0.5 * (x1 + x2), 0.5 * (y1 + y2))

    def area(self):
        x1, y1, x2, y2 = self.bbox_xyxy
        return max(0.0, x2 - x1) * max(0.0, y2 - y1)


def iou_xyxy(a, b):
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b

    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)

    iw = max(0.0, ix2 - ix1)
    ih = max(0.0, iy2 - iy1)
    inter = iw * ih

    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)

    denom = area_a + area_b - inter + 1e-9
    return inter / denom


def nms(dets, iou_thres):
    dets = sorted(dets, key=lambda d: d.conf, reverse=True)
    keep = []

    for d in dets:
        ok = True
        for k in keep:
            if iou_xyxy(d.bbox_xyxy, k.bbox_xyxy) > iou_thres:
                ok = False
                break
        if ok:
            keep.append(d)

    return keep


class YOLODetector:
    """
    ONNX YOLO detector + motion-based post-filter + short-term persistence.

    Mantık:
    - YOLO her zaman orijinal görüntüde çalışır.
    - Motion mask ayrı hesaplanır.
    - Detection kutusu çevresindeki hareket oranı yeterli değilse detection elenir.
    - Track varken eşikler gevşer.
    - Kısa süreli kaçırmalarda önceki track korunur.
    """

    def __init__(
        self,
        onnx_path: str,
        input_size: int,
        conf_thres: float,
        iou_thres: float,
        class_name: str,
        providers=None
    ):
        self.onnx_path = onnx_path
        self.input_size = 320  # istersen input_size kullanabilirsin
        self.conf_thres = conf_thres
        self.iou_thres = iou_thres
        self.class_name = class_name

        cpu_providers = ['CPUExecutionProvider']

        options = ort.SessionOptions()
        options.intra_op_num_threads = 4
        options.inter_op_num_threads = 4
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

        self.sess = ort.InferenceSession(
            onnx_path,
            sess_options=options,
            providers=cpu_providers
        )

        self.in_name = self.sess.get_inputs()[0].name
        self.out_names = [o.name for o in self.sess.get_outputs()]
        self.input_shape = self.sess.get_inputs()[0].shape

        # -----------------------------
        # Motion filter ayarları
        # -----------------------------
        self.use_motion_filter = True
        self.motion_threshold = 25
        self.motion_min_area = 20
        self.prev_gray = None
        self.last_motion_mask = None

        # Çok küçük kutularda motion filtresi agresif olmasın
        self.min_box_area_for_motion_check = 25

        # Motion box genişletme katsayısı
        self.motion_expand_scale = 1.8

        # Search mode / Track mode motion eşikleri
        self.min_motion_ratio_new = 0.03
        self.min_motion_ratio_tracked = 0.01

        # Search mode / Track mode confidence eşikleri
        self.conf_thres_new = self.conf_thres
        self.conf_thres_tracked = max(0.10, self.conf_thres * 0.6)

        # Kısa süreli track kaybı toleransı
        self.last_confirmed_detection = None
        self.track_miss_count = 0
        self.max_track_miss = 4

    def _letterbox_fast(self, img):
        h, w = img.shape[:2]
        s = self.input_size

        scale = s / max(h, w)
        nw = int(w * scale)
        nh = int(h * scale)

        resized = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)

        canvas = np.full((s, s, 3), 114, dtype=np.uint8)
        pad_x = (s - nw) // 2
        pad_y = (s - nh) // 2
        canvas[pad_y:pad_y + nh, pad_x:pad_x + nw] = resized

        return canvas, scale, pad_x, pad_y

    def _estimate_global_motion(self, prev_gray, curr_gray):
        """
        Önceki ve mevcut frame arasında global hareketi affine olarak tahmin eder.
        Başarısız olursa identity döner.
        """
        pts_prev = cv2.goodFeaturesToTrack(
            prev_gray,
            maxCorners=300,
            qualityLevel=0.01,
            minDistance=7,
            blockSize=7
        )

        if pts_prev is None or len(pts_prev) < 8:
            return np.array([[1, 0, 0], [0, 1, 0]], dtype=np.float32)

        pts_curr, status, _ = cv2.calcOpticalFlowPyrLK(
            prev_gray,
            curr_gray,
            pts_prev,
            None
        )

        if pts_curr is None or status is None:
            return np.array([[1, 0, 0], [0, 1, 0]], dtype=np.float32)

        good_prev = pts_prev[status.flatten() == 1]
        good_curr = pts_curr[status.flatten() == 1]

        if len(good_prev) < 8 or len(good_curr) < 8:
            return np.array([[1, 0, 0], [0, 1, 0]], dtype=np.float32)

        M, _ = cv2.estimateAffinePartial2D(
            good_prev,
            good_curr,
            method=cv2.RANSAC,
            ransacReprojThreshold=3.0
        )

        if M is None:
            M = np.array([[1, 0, 0], [0, 1, 0]], dtype=np.float32)

        return M.astype(np.float32)

    def _create_motion_mask(self, prev_gray, curr_gray):
        """
        Kamera hareketini bastırıp residual motion mask üretir.
        """
        h, w = curr_gray.shape[:2]

        M = self._estimate_global_motion(prev_gray, curr_gray)

        aligned_prev = cv2.warpAffine(
            prev_gray,
            M,
            (w, h),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REPLICATE
        )

        diff = cv2.absdiff(curr_gray, aligned_prev)
        diff = cv2.GaussianBlur(diff, (5, 5), 0)

        _, motion_mask = cv2.threshold(
            diff,
            self.motion_threshold,
            255,
            cv2.THRESH_BINARY
        )

        kernel_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        kernel_dilate = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))

        motion_mask = cv2.morphologyEx(motion_mask, cv2.MORPH_OPEN, kernel_open)
        motion_mask = cv2.dilate(motion_mask, kernel_dilate, iterations=1)

        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(motion_mask, 8)
        cleaned = np.zeros_like(motion_mask)

        for i in range(1, num_labels):
            area = stats[i, cv2.CC_STAT_AREA]
            if area >= self.motion_min_area:
                cleaned[labels == i] = 255

        return cleaned

    def _update_motion_mask(self, bgr):
        """
        Motion mask üretir ve self.last_motion_mask içine kaydeder.
        YOLO input'unu değiştirmez.
        """
        curr_gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

        if self.prev_gray is None:
            self.prev_gray = curr_gray.copy()
            self.last_motion_mask = np.zeros_like(curr_gray, dtype=np.uint8)
            return

        motion_mask = self._create_motion_mask(self.prev_gray, curr_gray)
        self.prev_gray = curr_gray.copy()
        self.last_motion_mask = motion_mask

    def _expand_bbox(self, bbox_xyxy, img_w, img_h, scale=1.8):
        x1, y1, x2, y2 = bbox_xyxy
        cx = 0.5 * (x1 + x2)
        cy = 0.5 * (y1 + y2)
        bw = (x2 - x1) * scale
        bh = (y2 - y1) * scale

        nx1 = max(0, int(cx - bw / 2.0))
        ny1 = max(0, int(cy - bh / 2.0))
        nx2 = min(img_w, int(cx + bw / 2.0))
        ny2 = min(img_h, int(cy + bh / 2.0))
        return (nx1, ny1, nx2, ny2)

    def _motion_ratio_in_box(self, bbox_xyxy, motion_mask):
        """
        Detection kutusunun biraz genişletilmiş hali içinde hareket oranını hesaplar.
        """
        if motion_mask is None:
            return 1.0

        H, W = motion_mask.shape[:2]
        ex1, ey1, ex2, ey2 = self._expand_bbox(
            bbox_xyxy,
            W,
            H,
            scale=self.motion_expand_scale
        )

        if ex2 <= ex1 or ey2 <= ey1:
            return 0.0

        roi = motion_mask[ey1:ey2, ex1:ex2]
        if roi.size == 0:
            return 0.0

        box_area = roi.shape[0] * roi.shape[1]
        if box_area < self.min_box_area_for_motion_check:
            return 1.0

        moving_pixels = np.count_nonzero(roi > 0)
        return moving_pixels / float(box_area)

    def _filter_detections_by_motion(self, dets, motion_mask, last_track=None):
        """
        Detection'ları kutu içi hareket oranına göre filtreler.
        Track varken eşik gevşetilir.
        """
        if motion_mask is None or len(dets) == 0:
            return dets

        kept = []

        for d in dets:
            ratio = self._motion_ratio_in_box(d.bbox_xyxy, motion_mask)

            threshold = self.min_motion_ratio_new
            if last_track is not None:
                threshold = self.min_motion_ratio_tracked

            if ratio >= threshold:
                kept.append(d)

        return kept

    def detect(self, bgr, last_track=None):
        """
        last_track:
            Eğer bir önceki karede drone bulunduysa, onun koordinatlarını gönderir.
        """
        if self.use_motion_filter:
            self._update_motion_mask(bgr)

        roi_offset = (0, 0)
        inference_img = bgr
        actual_shape = bgr.shape
        motion_mask_for_filter = self.last_motion_mask

        # --- ROI SEÇİMİ ---
        if last_track is not None:
            x1_t, y1_t, x2_t, y2_t = last_track.bbox_xyxy
            cx = (x1_t + x2_t) / 2.0
            cy = (y1_t + y2_t) / 2.0

            roi_size = 320
            H, W = bgr.shape[:2]

            roi_w = min(roi_size, W)
            roi_h = min(roi_size, H)

            r_x1 = int(np.clip(cx - roi_w // 2, 0, max(0, W - roi_w)))
            r_y1 = int(np.clip(cy - roi_h // 2, 0, max(0, H - roi_h)))

            inference_img = bgr[r_y1:r_y1 + roi_h, r_x1:r_x1 + roi_w]
            roi_offset = (r_x1, r_y1)
            actual_shape = inference_img.shape

            if motion_mask_for_filter is not None:
                motion_mask_for_filter = motion_mask_for_filter[
                    r_y1:r_y1 + roi_h,
                    r_x1:r_x1 + roi_w
                ]

        # --- PRE-PROCESSING ---
        inference_img = cv2.GaussianBlur(inference_img, (3, 3), 0)
        img, scale, pad_x, pad_y = self._letterbox_fast(inference_img)

        rgb = img[..., ::-1].transpose(2, 0, 1)
        x = np.ascontiguousarray(rgb[None, ...], dtype=np.float32) / 255.0

        # --- INFERENCE ---
        outs = self.sess.run(self.out_names, {self.in_name: x})

        # Search mode / Track mode confidence seçimi
        conf_used = self.conf_thres_new if last_track is None else self.conf_thres_tracked

        # --- POST-PROCESSING ---
        dets = self._postprocess_fast(
            outs,
            actual_shape,
            scale,
            pad_x,
            pad_y,
            conf_override=conf_used
        )

        # Motion tabanlı filtre
        if self.use_motion_filter:
            dets = self._filter_detections_by_motion(
                dets,
                motion_mask_for_filter,
                last_track=last_track
            )

        # ROI kullanıldıysa koordinatları orijinal tam resme geri taşı
        if last_track is not None and len(dets) > 0:
            translated = []
            ox, oy = roi_offset

            for d in dets:
                nx1, ny1, nx2, ny2 = d.bbox_xyxy
                translated_bbox = (nx1 + ox, ny1 + oy, nx2 + ox, ny2 + oy)
                translated.append(
                    Detection(translated_bbox, d.conf, d.class_id, d.class_name)
                )
            dets = translated

        # -----------------------------------------
        # Kısa süreli kayıplarda track'i koru
        # -----------------------------------------
        if len(dets) > 0:
            self.last_confirmed_detection = dets[0]
            self.track_miss_count = 0
            return dets

        if self.last_confirmed_detection is not None and self.track_miss_count < self.max_track_miss:
            self.track_miss_count += 1
            return [self.last_confirmed_detection]

        self.last_confirmed_detection = None
        self.track_miss_count = 0
        return []

    def _postprocess_fast(self, outs, img_shape, scale, pad_x, pad_y, conf_override=None):
        y = outs[0][0]

        # Bazı exportlarda shape [5, N] gelebiliyor
        if len(y.shape) == 2 and y.shape[0] == 5:
            y = y.T

        conf_thr = self.conf_thres if conf_override is None else conf_override

        scores = y[:, 4]
        mask = scores >= conf_thr

        if not np.any(mask):
            return []

        filtered = y[mask]
        confidences = filtered[:, 4]

        cxs = filtered[:, 0]
        cys = filtered[:, 1]
        wws = filtered[:, 2]
        hhs = filtered[:, 3]

        x1 = (cxs - wws / 2.0 - pad_x) / scale
        y1 = (cys - hhs / 2.0 - pad_y) / scale
        x2 = (cxs + wws / 2.0 - pad_x) / scale
        y2 = (cys + hhs / 2.0 - pad_y) / scale

        H, W = img_shape[:2]
        x1 = np.clip(x1, 0, W - 1)
        y1 = np.clip(y1, 0, H - 1)
        x2 = np.clip(x2, 0, W - 1)
        y2 = np.clip(y2, 0, H - 1)

        all_dets = []
        for i in range(len(filtered)):
            bbox = (float(x1[i]), float(y1[i]), float(x2[i]), float(y2[i]))
            all_dets.append(
                Detection(bbox, float(confidences[i]), 0, self.class_name)
            )

        # İstersen gerçek NMS açabilirsin:
        # all_dets = nms(all_dets, self.iou_thres)

        # Şu an tek sınıf drone takip için en yüksek confident olanı döndür
        if all_dets:
            return [max(all_dets, key=lambda d: d.conf)]

        return []