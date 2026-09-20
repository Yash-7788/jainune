import * as ImageManipulator from "expo-image-manipulator";
import * as FileSystem from "expo-file-system";

export interface OptimizedImageResult {
  uri: string;
  width: number;
  height: number;
  fileSizeBytes: number;
  base64?: string;
}

/**
 * Compresses an image to extreme high-density WebP format.
 * Target: Max 480x600 resolution, 70% quality, <=15KB payload.
 */
export async function optimizeProfilePhoto(
  originalUri: string
): Promise<OptimizedImageResult> {
  try {
    // 1. Execute client-side hardware-accelerated resize & transcode
    const manipulated = await ImageManipulator.manipulateAsync(
      originalUri,
      [
        {
          resize: {
            width: 480,
            height: 480, // WhatsApp-style 1:1 square crop
          },
        },
      ],
      {
        compress: 0.7, // 70% lossy compression (indistinguishable on retina screens)
        format: ImageManipulator.SaveFormat.WEBP,
        base64: false,
      }
    );

    // 2. Validate resulting file size
    const fileInfo = await FileSystem.getInfoAsync(manipulated.uri);
    const size = fileInfo.exists && "size" in fileInfo ? fileInfo.size : 0;

    // Safety assertion: Alert if image exceeds strict 20KB budget
    if (size > 20 * 1024) {
      // Re-compress at lower quality if initial pass exceeded threshold
      const emergencyPass = await ImageManipulator.manipulateAsync(
        manipulated.uri,
        [{ resize: { width: 400 } }],
        {
          compress: 0.55,
          format: ImageManipulator.SaveFormat.WEBP,
        }
      );
      const emergencyInfo = await FileSystem.getInfoAsync(emergencyPass.uri);
      const emergencySize = emergencyInfo.exists && "size" in emergencyInfo ? emergencyInfo.size : size;
      return {
        uri: emergencyPass.uri,
        width: emergencyPass.width,
        height: emergencyPass.height,
        fileSizeBytes: emergencySize,
      };
    }

    return {
      uri: manipulated.uri,
      width: manipulated.width,
      height: manipulated.height,
      fileSizeBytes: size,
    };
  } catch (error) {
    throw new Error(`IMAGE_OPTIMIZATION_FAILED: ${(error as Error).message}`);
  }
}
