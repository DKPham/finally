export class MockEventSource {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSED = 2;
  static instances: MockEventSource[] = [];
  static reset() {
    MockEventSource.instances = [];
  }
  static latest(): MockEventSource {
    return MockEventSource.instances[MockEventSource.instances.length - 1];
  }

  url: string;
  readyState = MockEventSource.CONNECTING;
  onopen: ((ev: Event) => void) | null = null;
  onmessage: ((ev: MessageEvent) => void) | null = null;
  onerror: ((ev: Event) => void) | null = null;
  closed = false;

  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
  }
  open() {
    this.readyState = MockEventSource.OPEN;
    this.onopen?.(new Event("open"));
  }
  emit(data: unknown) {
    this.onmessage?.(new MessageEvent("message", { data: JSON.stringify(data) }));
  }
  fail(closed = false) {
    this.readyState = closed ? MockEventSource.CLOSED : MockEventSource.CONNECTING;
    this.onerror?.(new Event("error"));
  }
  close() {
    this.closed = true;
    this.readyState = MockEventSource.CLOSED;
  }
}
