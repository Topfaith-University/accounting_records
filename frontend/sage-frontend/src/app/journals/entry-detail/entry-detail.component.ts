import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, Router } from '@angular/router';
import { JournalsService } from '../../services/journals.service';

@Component({
  selector: 'app-entry-detail',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './entry-detail.component.html',
})
export class EntryDetailComponent implements OnInit {
  entry: any = null;
  loading = true;
  error = '';
  actionError = '';

  get canEditDraft(): boolean {
    return !!this.entry && this.entry.status === 'DRAFT';
  }

  constructor(
    private route: ActivatedRoute,
    private router: Router,
    private journalsService: JournalsService,
  ) {}

  async ngOnInit() {
    const id = this.route.snapshot.paramMap.get('id')!;
    try {
      this.entry = await this.journalsService.getEntry(id);
    } catch { this.error = 'Entry not found.'; }
    finally { this.loading = false; }
  }

  async postEntry() {
    try {
      this.entry = await this.journalsService.postEntry(this.entry.entry_id);
      this.actionError = '';
    } catch (e: any) {
      this.actionError = e.response?.data?.detail ?? 'Post failed.';
    }
  }

  async voidEntry() {
    if (!confirm('Void this entry? This cannot be undone.')) return;
    try {
      this.entry = await this.journalsService.voidEntry(this.entry.entry_id);
      this.actionError = '';
    } catch (e: any) {
      this.actionError = e.response?.data?.detail ?? 'Void failed.';
    }
  }

  editEntry() {
    this.router.navigate(['/journals', this.entry.entry_id, 'edit']);
  }

  async deleteEntry() {
    if (!confirm('Delete this draft entry? This cannot be undone.')) return;
    try {
      await this.journalsService.deleteEntry(this.entry.entry_id);
      this.router.navigate(['/journals']);
    } catch (e: any) {
      this.actionError = e.response?.data?.detail ?? 'Delete failed.';
    }
  }

  statusColor(s: string) {
    return { DRAFT: '#f59e0b', POSTED: '#10b981', VOID: '#ef4444' }[s] ?? '#888';
  }
}
