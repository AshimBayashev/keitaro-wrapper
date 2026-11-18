import { ApplicationConfig, LOCALE_ID, provideBrowserGlobalErrorListeners } from '@angular/core';
import { provideHttpClient } from '@angular/common/http';
import { registerLocaleData } from '@angular/common';
import ru from '@angular/common/locales/ru';
import { provideNzI18n, ru_RU } from 'ng-zorro-antd/i18n';

registerLocaleData(ru);

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideHttpClient(),
    provideNzI18n(ru_RU),
    { provide: LOCALE_ID, useValue: 'ru-RU' },
  ],
};
