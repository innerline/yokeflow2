import { main } from '../src/index';

describe('main', () => {
  it('should return greeting', () => {
    expect(main()).toBe('Hello, World!');
  });
});
