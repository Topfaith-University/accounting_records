import { Component, Input, Output, EventEmitter } from '@angular/core';

@Component({
  selector: 'app-pagination',
  standalone: true,
  imports: [],
  template: `
    @if (total > pageSize) {
      <div class="pag-bar">
        <span class="pag-info">Showing {{ from }}–{{ to }} of {{ total }}</span>
        <div class="pag-controls">
          <button class="pag-btn" (click)="prev()" [disabled]="page <= 1">← Prev</button>
          <span class="pag-pages">{{ page }} / {{ totalPages }}</span>
          <button class="pag-btn" (click)="next()" [disabled]="page >= totalPages">Next →</button>
        </div>
      </div>
    }
  `,
  styles: [`
    .pag-bar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: .625rem 1rem;
      background: var(--canvas, #f0f4fb);
      border-top: 1px solid var(--border, #e2e8f0);
      font-size: .8rem;
      font-family: var(--font-body, sans-serif);
    }
    .pag-info { color: var(--text-muted, #6b7280); }
    .pag-controls { display: flex; align-items: center; gap: .5rem; }
    .pag-pages { color: var(--text-secondary, #374151); font-weight: 600; padding: 0 .25rem; }
    .pag-btn {
      padding: .3rem .7rem;
      border: 1.5px solid var(--border, #e2e8f0);
      border-radius: 4px;
      background: white;
      color: var(--text-secondary, #374151);
      font-size: .8rem;
      font-weight: 700;
      cursor: pointer;
      transition: border-color 150ms, color 150ms;
    }
    .pag-btn:hover:not(:disabled) {
      border-color: var(--navy-primary, #314991);
      color: var(--navy-primary, #314991);
    }
    .pag-btn:disabled { opacity: .4; cursor: not-allowed; }
  `]
})
export class PaginationComponent {
  @Input() total = 0;
  @Input() page = 1;
  @Input() pageSize = 25;
  @Output() pageChange = new EventEmitter<number>();

  get totalPages() { return Math.max(1, Math.ceil(this.total / this.pageSize)); }
  get from() { return this.total === 0 ? 0 : (this.page - 1) * this.pageSize + 1; }
  get to() { return Math.min(this.page * this.pageSize, this.total); }

  prev() { if (this.page > 1) this.pageChange.emit(this.page - 1); }
  next() { if (this.page < this.totalPages) this.pageChange.emit(this.page + 1); }
}
