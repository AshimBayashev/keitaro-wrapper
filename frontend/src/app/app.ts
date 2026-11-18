import { Component, OnInit, signal } from '@angular/core';
import { HttpClient, HttpErrorResponse, HttpParams } from '@angular/common/http';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { firstValueFrom } from 'rxjs';
import { NzButtonModule } from 'ng-zorro-antd/button';
import { NzInputModule } from 'ng-zorro-antd/input';
import { NzSelectModule } from 'ng-zorro-antd/select';

type Option = { id: number; name: string };
type Country = { code: string; name: string };
type Meta = { countries: Country[]; domains: Option[]; groups: Option[]; sources: Option[]; offers: Option[] };
type Campaign = {
  id: number;
  name: string;
  alias: string;
  state: string;
  domain_id: number | null;
  group_id: number | null;
  traffic_source_id: number | null;
};
type StreamOffer = { id: number; name: string; share: number; state: string; percentage: number };
type Stream = {
  id: number;
  name: string;
  type: string;
  schema: string;
  state: string;
  position: number;
  revision: string;
  action_payload: string;
  filters: { name: string; mode: string; payload: string[] }[];
  offers: StreamOffer[];
};
type Detail = { campaign: Campaign; streams: Stream[] };

@Component({
  imports: [CommonModule, FormsModule, NzButtonModule, NzInputModule, NzSelectModule],
  selector: 'app-root',
  styleUrl: './app.css',
  templateUrl: './app.html',
})
export class App implements OnInit {
  readonly meta = signal<Meta | null>(null);
  readonly countries = signal<Country[]>([]);
  readonly campaigns = signal<Campaign[]>([]);
  readonly detail = signal<Detail | null>(null);
  readonly prefix = signal('test_bayashev_');
  readonly loading = signal(true);
  readonly busy = signal(false);
  readonly loadingDetail = signal(false);
  readonly error = signal('');
  readonly notice = signal('');
  readonly view = signal<'create' | 'edit'>('create');
  readonly hasMore = signal(false);
  readonly nextOffset = signal(0);
  form = { suffix: '', geo: '', offer_id: 0, domain_id: 0, group_id: 0, traffic_source_id: 0 };
  campaignQuery = '';
  directCampaignId = '';
  selectedStreamId = 0;
  newOfferId = 0;
  confirmRemoveId = 0;

  constructor(private readonly http: HttpClient) {}

  async ngOnInit(): Promise<void> {
    await this.loadInitial();
  }
  get fullName(): string {
    return this.prefix() + this.form.suffix.trim();
  }
  get filteredCampaigns(): Campaign[] {
    const q = this.campaignQuery.trim().toLocaleLowerCase();
    return q
      ? this.campaigns().filter((c) => `${c.name} ${c.id}`.toLocaleLowerCase().includes(q))
      : this.campaigns();
  }
  get selectedStream(): Stream | undefined {
    return this.detail()?.streams.find((s) => s.id === this.selectedStreamId);
  }
  get availableOffers(): Option[] {
    const selected = new Set(this.selectedStream?.offers.map((o) => o.id) ?? []);
    return this.meta()?.offers.filter((o) => !selected.has(o.id)) ?? [];
  }
  get activeOfferCount(): number {
    return (
      this.detail()?.streams.reduce(
        (n, s) => n + s.offers.filter((o) => o.state === 'active').length,
        0,
      ) ?? 0
    );
  }
  optionName(options: Option[] | undefined, id: number | null): string {
    return options?.find((o) => o.id === id)?.name ?? (id ? `#${id}` : '—');
  }
  private message(error: unknown): string {
    if (error instanceof HttpErrorResponse) {
      if (typeof error.error?.detail === 'string') return error.error.detail;
      if (error.status === 0)
        return 'API недоступен. Проверьте, что FastAPI запущен на порту 8000.';
    }
    return 'Не удалось выполнить действие. Обновите данные и повторите попытку.';
  }
  clearFeedback(): void {
    this.error.set('');
    this.notice.set('');
  }

  async loadInitial(): Promise<void> {
    this.loading.set(true);
    this.clearFeedback();
    try {
      const [config, meta, page] = await Promise.all([
        firstValueFrom(this.http.get<{ name_prefix: string }>('/api/config')),
        firstValueFrom(this.http.get<Meta>('/api/meta')),
        firstValueFrom(
          this.http.get<{ items: Campaign[]; has_more: boolean; next_offset: number }>(
            '/api/campaigns',
          ),
        ),
      ]);
      this.prefix.set(config.name_prefix);
      this.meta.set(meta);
      const displayNames = typeof Intl.DisplayNames === 'function'
        ? new Intl.DisplayNames(['ru'], { type: 'region' })
        : null;
      const collator = new Intl.Collator('ru');
      this.countries.set(
        meta.countries
          .map((country) => ({
            code: country.code,
            name: displayNames?.of(country.code) ?? country.name,
          }))
          .sort((left, right) => collator.compare(left.name, right.name)),
      );
      this.campaigns.set(page.items);
      this.hasMore.set(page.has_more);
      this.nextOffset.set(page.next_offset);
      this.form.domain_id = meta.domains[0]?.id ?? 0;
      this.form.group_id =
        meta.groups.find((x) => x.name.startsWith(config.name_prefix))?.id ??
        meta.groups[0]?.id ??
        0;
      this.form.traffic_source_id = meta.sources[0]?.id ?? 0;
      this.form.offer_id = meta.offers[0]?.id ?? 0;
    } catch (error) {
      this.error.set(this.message(error));
    } finally {
      this.loading.set(false);
    }
  }

  async loadMore(): Promise<void> {
    if (!this.hasMore() || this.busy()) return;
    this.busy.set(true);
    this.clearFeedback();
    try {
      const page = await firstValueFrom(
        this.http.get<{ items: Campaign[]; has_more: boolean; next_offset: number }>(
          '/api/campaigns',
          { params: new HttpParams().set('offset', this.nextOffset()) },
        ),
      );
      this.campaigns.update((items) => [...items, ...page.items]);
      this.hasMore.set(page.has_more);
      this.nextOffset.set(page.next_offset);
    } catch (error) {
      this.error.set(this.message(error));
    } finally {
      this.busy.set(false);
    }
  }

  async openCampaign(id: number): Promise<void> {
    this.view.set('edit');
    this.loadingDetail.set(true);
    this.detail.set(null);
    this.clearFeedback();
    try {
      const detail = await firstValueFrom(this.http.get<Detail>(`/api/campaigns/${id}`));
      this.detail.set(detail);
      this.selectedStreamId =
        detail.streams.find((s) => s.schema === 'landings' && s.state === 'active')?.id ?? 0;
      this.newOfferId = 0;
      this.confirmRemoveId = 0;
    } catch (error) {
      this.error.set(this.message(error));
    } finally {
      this.loadingDetail.set(false);
    }
  }
  async refreshDetail(): Promise<void> {
    const id = this.detail()?.campaign.id;
    if (id) await this.openCampaign(id);
  }
  openById(): void {
    const id = Number(this.directCampaignId);
    if (!Number.isSafeInteger(id) || id <= 0) {
      this.error.set('Введите числовой ID кампании.');
      return;
    }
    void this.openCampaign(id);
  }

  async createCampaign(): Promise<void> {
    if (this.busy()) return;
    this.clearFeedback();
    if (
      !this.form.suffix.trim() ||
      !this.countries().some((country) => country.code === this.form.geo) ||
      !this.form.offer_id ||
      !this.form.domain_id ||
      !this.form.group_id ||
      !this.form.traffic_source_id
    ) {
      this.error.set('Заполните окончание названия, выберите страну и все настройки кампании.');
      return;
    }
    this.busy.set(true);
    let createdId: number | undefined;
    try {
      const result = await firstValueFrom(
        this.http.post<{ id: number; warning: string | null }>('/api/campaigns', {
          name: this.fullName,
          geo: this.form.geo,
          offer_id: Number(this.form.offer_id),
          domain_id: Number(this.form.domain_id),
          group_id: Number(this.form.group_id),
          traffic_source_id: Number(this.form.traffic_source_id),
        }),
      );
      createdId = result.id;
      this.form.suffix = '';
      const page = await firstValueFrom(
        this.http.get<{ items: Campaign[]; has_more: boolean; next_offset: number }>(
          '/api/campaigns',
        ),
      );
      this.campaigns.set(page.items);
      this.hasMore.set(page.has_more);
      this.nextOffset.set(page.next_offset);
      await this.openCampaign(result.id);
      this.notice.set(result.warning ?? `Кампания #${result.id} создана и активна в Keitaro.`);
    } catch (error) {
      this.error.set(
        createdId
          ? `Кампания #${createdId} создана, но обновить экран не удалось. Откройте её по ID. ${this.message(error)}`
          : this.message(error),
      );
    } finally {
      this.busy.set(false);
    }
  }

  async addOffer(): Promise<void> {
    const stream = this.selectedStream;
    if (!stream || !this.newOfferId || this.busy()) return;
    this.busy.set(true);
    this.clearFeedback();
    try {
      await firstValueFrom(
        this.http.post(`/api/streams/${stream.id}/offers`, {
          offer_id: Number(this.newOfferId),
          expected_revision: stream.revision,
        }),
      );
      const id = this.detail()!.campaign.id;
      await this.openCampaign(id);
      this.notice.set('Оффер добавлен. Доли трафика обновлены из Keitaro.');
    } catch (error) {
      this.error.set(this.message(error));
    } finally {
      this.busy.set(false);
    }
  }

  async removeOffer(offer: StreamOffer): Promise<void> {
    const stream = this.selectedStream;
    if (!stream || this.busy()) return;
    this.busy.set(true);
    this.clearFeedback();
    try {
      const params = new HttpParams().set('expected_revision', stream.revision);
      await firstValueFrom(
        this.http.delete(`/api/streams/${stream.id}/offers/${offer.id}`, { params }),
      );
      const id = this.detail()!.campaign.id;
      await this.openCampaign(id);
      this.notice.set(`Оффер «${offer.name}» удалён из потока.`);
    } catch (error) {
      this.error.set(this.message(error));
    } finally {
      this.busy.set(false);
      this.confirmRemoveId = 0;
    }
  }
}
