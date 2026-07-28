import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule, FormBuilder, FormGroup, FormArray, Validators } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { JournalsService } from '../../services/journals.service';
import { AccountsService } from '../../services/accounts.service';
import { AccountSelectComponent } from '../../shared/account-select/account-select.component';

@Component({
  selector: 'app-entry-form',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, AccountSelectComponent],
  templateUrl: './entry-form.component.html',
})
export class EntryFormComponent implements OnInit {
  form!: FormGroup;
  allAccounts: any[] = [];
  saving = false;
  posting = false;
  error = '';
  entryId: string | null = null;

  get isEditMode(): boolean { return !!this.entryId; }
  get lines(): FormArray { return this.form.get('lines') as FormArray; }

  get totalAmount(): number {
    return this.lines.controls.reduce((sum, l) => sum + (Number(l.value.amount) || 0), 0);
  }

  get isBalanced(): boolean {
    return this.lines.length >= 1 &&
      this.lines.controls.every(l =>
        l.value.from_account_id && l.value.to_account_id && Number(l.value.amount) > 0
      );
  }

  constructor(
    private fb: FormBuilder,
    private journalsService: JournalsService,
    private accountsService: AccountsService,
    private route: ActivatedRoute,
    private router: Router,
  ) {}

  async ngOnInit() {
    this.form = this.fb.group({
      date: [new Date().toISOString().slice(0, 10), Validators.required],
      entry_type: ['MANUAL'],
      lines: this.fb.array([]),
    });
    try {
      const data = await this.accountsService.getAll();
      this.allAccounts = data.results ?? data;
      this.entryId = this.route.snapshot.paramMap.get('id');
      if (this.entryId) {
        const entry = await this.journalsService.getEntry(this.entryId);
        this.form.patchValue({
          date: entry.date ?? '',
          entry_type: entry.entry_type ?? 'MANUAL',
        });
        this.lines.clear();
        // Pair DEBIT lines with CREDIT lines by index
        const debitLines = (entry.lines ?? []).filter((l: any) => l.side === 'DEBIT');
        const creditLines = (entry.lines ?? []).filter((l: any) => l.side === 'CREDIT');
        const count = Math.max(debitLines.length, creditLines.length);
        for (let i = 0; i < count; i++) {
          this.lines.push(this.fb.group({
            from_account_id: [debitLines[i]?.account_id ?? '', Validators.required],
            to_account_id:   [creditLines[i]?.account_id ?? '', Validators.required],
            amount:      [debitLines[i]?.amount ?? creditLines[i]?.amount ?? null, [Validators.required, Validators.min(0.01)]],
            description: [debitLines[i]?.description ?? creditLines[i]?.description ?? ''],
          }));
        }
      }
      if (this.lines.length === 0) {
        this.addLine();
      }
    } catch {
      this.error = 'Failed to load journal entry form. Please refresh.';
    }
  }

  addLine() {
    this.lines.push(this.fb.group({
      from_account_id: ['', Validators.required],
      to_account_id:   ['', Validators.required],
      amount:      [null, [Validators.required, Validators.min(0.01)]],
      description: [''],
    }));
  }

  removeLine(i: number) {
    if (this.lines.length > 1) this.lines.removeAt(i);
  }

  private buildPayload() {
    const val = this.form.value;
    const lines: any[] = [];
    const descriptions: string[] = [];
    for (const row of val.lines) {
      const amt = Number(row.amount);
      if (amt > 0 && row.from_account_id && row.to_account_id) {
        const desc = (row.description || '').trim();
        lines.push({ account_id: row.from_account_id, side: 'DEBIT',  amount: amt, description: desc });
        lines.push({ account_id: row.to_account_id,   side: 'CREDIT', amount: amt, description: desc });
        if (desc) descriptions.push(desc);
      }
    }
    const entryDescription = descriptions.join('; ') || 'Journal Entry';
    return { date: val.date, description: entryDescription, entry_type: val.entry_type, lines };
  }

  async save() {
    if (!this.form.valid || !this.isBalanced) return;
    this.saving = true;
    this.error = '';
    try {
      const entry = this.entryId
        ? await this.journalsService.updateEntry(this.entryId, this.buildPayload())
        : await this.journalsService.createEntry(this.buildPayload());
      this.router.navigate(['/journals', entry.entry_id]);
    } catch (e: any) {
      this.error = e.response?.data?.detail ?? (e.response?.data ? JSON.stringify(e.response.data) : 'Save failed.');
    } finally { this.saving = false; }
  }

  async saveAndPost() {
    if (!this.form.valid || !this.isBalanced) return;
    this.posting = true;
    this.error = '';
    try {
      const entry = this.entryId
        ? await this.journalsService.updateEntry(this.entryId, this.buildPayload())
        : await this.journalsService.createEntry(this.buildPayload());
      await this.journalsService.postEntry(entry.entry_id);
      this.router.navigate(['/journals', entry.entry_id]);
    } catch (e: any) {
      this.error = e.response?.data?.detail ?? (e.response?.data ? JSON.stringify(e.response.data) : 'Post failed.');
    } finally { this.posting = false; }
  }
}
