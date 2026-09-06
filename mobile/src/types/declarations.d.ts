declare module "react-native-razorpay" {
  export interface RazorpayCheckoutOptions {
    description?: string;
    image?: string;
    currency: string;
    key: string;
    amount: string | number;
    name: string;
    order_id: string;
    prefill?: {
      email?: string;
      contact?: string;
      name?: string;
    };
    theme?: {
      color?: string;
    };
    modal?: {
      backdropclose?: boolean;
      [key: string]: any;
    };
    [key: string]: any;
  }

  export interface RazorpaySuccessData {
    razorpay_payment_id: string;
    razorpay_order_id: string;
    razorpay_signature: string;
  }

  export interface RazorpayErrorData {
    code: number;
    description: string;
    source?: string;
    step?: string;
    reason?: string;
    metadata?: Record<string, any>;
  }

  export default class RazorpayCheckout {
    static open(
      options: RazorpayCheckoutOptions
    ): Promise<RazorpaySuccessData>;
  }
}

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
