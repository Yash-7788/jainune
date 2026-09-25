declare module "expo-splash-screen" {
  export function preventAutoHideAsync(): Promise<boolean>;
  export function hideAsync(): Promise<boolean>;
}

declare module "expo-linking" {
  export function openURL(url: string): Promise<boolean>;
  export function canOpenURL(url: string): Promise<boolean>;
  export function createURL(path: string, options?: any): string;
  export function parse(url: string): {
    scheme: string | null;
    hostname: string | null;
    path: string | null;
    queryParams: Record<string, string | undefined>;
  };
  export function addEventListener(
    type: "url",
    listener: (event: { url: string }) => void
  ): { remove: () => void };
}

declare module "@react-native-community/slider" {
  import { Component } from "react";
  import { ViewProps } from "react-native";

  export interface SliderProps extends ViewProps {
    value?: number;
    step?: number;
    minimumValue?: number;
    maximumValue?: number;
    minimumTrackTintColor?: string;
    maximumTrackTintColor?: string;
    thumbTintColor?: string;
    onValueChange?: (value: number) => void;
    onSlidingComplete?: (value: number) => void;
    disabled?: boolean;
    style?: any;
  }

  export default class Slider extends Component<SliderProps> {}
}

declare module "expo-image-manipulator" {
  export enum SaveFormat {
    JPEG = "jpeg",
    PNG = "png",
    WEBP = "webp",
  }

  export interface ActionResize {
    resize: {
      width?: number;
      height?: number;
    };
  }

  export type Action =
    | ActionResize
    | { rotate: number }
    | { flip: { vertical?: boolean; horizontal?: boolean } }
    | { crop: { originX: number; originY: number; width: number; height: number } };

  export interface SaveOptions {
    base64?: boolean;
    compress?: number;
    format?: SaveFormat;
  }

  export interface ImageResult {
    uri: string;
    width: number;
    height: number;
    base64?: string;
  }

  export function manipulateAsync(
    uri: string,
    actions?: Action[],
    saveOptions?: SaveOptions
  ): Promise<ImageResult>;
}

