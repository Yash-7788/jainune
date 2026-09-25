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
 * Compresses an image to high-density WebP format.
 * Target: Max 640x800 resolution (retina card/profile), 75% quality, <=45KB payload.
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
            width: 640,
            height: 800,
          },
        },
      ],
      {
        compress: 0.75, // 75% WebP quality
        format: ImageManipulator.SaveFormat.WEBP,
        base64: false,
      }
    );

    // 2. Validate resulting file size
    const fileInfo = await FileSystem.getInfoAsync(manipulated.uri);
    const size = fileInfo.exists && "size" in fileInfo ? fileInfo.size : 0;

    // Safety assertion: Alert if image exceeds strict 45KB budget
    if (size > 45 * 1024) {
      // Re-compress at lower quality if initial pass exceeded threshold
      const emergencyPass = await ImageManipulator.manipulateAsync(
        manipulated.uri,
        [{ resize: { width: 540 } }],
        {
          compress: 0.6,
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
